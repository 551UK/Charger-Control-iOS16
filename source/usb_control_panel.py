# 551UK direct USB input-current control panel. Imported by usb-currentd.
# This module makes NO CPU/GPU, thermal, battery-percentage or AppleChargeRateLimitIndex changes.
import base64
import contextlib
import fcntl
import html
import http.server
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

PORT=55127
HOST='127.0.0.1'
PRIVATE=Path('/var/jb/var/lib/551uk-usbcurrent')
STATE=PRIVATE/'active.json'
REQUESTED=PRIVATE/'requested-cap.json'
OPLOCK=PRIVATE/'operation.lock'
TOKENFILE=PRIVATE/'web-token'
POWER_MARKER=PRIVATE/'power-restart.json'
UIHTML=Path('/var/jb/usr/share/uk.551.chargingratetest/usb-control.html')
ICON=Path('/var/jb/usr/share/uk.551.chargingratetest/apple-touch-icon.png')
MIN_MA=500;MAX_MA=2400;STEP=100
GUARD=threading.RLock()
PING_INTERVAL=8
LOGFILE=None
CORE=None
_LAST_ERROR=''


def init(core,logfile):
    global CORE, LOGFILE
    CORE=core;LOGFILE=logfile
    PRIVATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    if PRIVATE.is_symlink():raise RuntimeError('Unsafe root state directory symlink')
    os.chown(PRIVATE,0,0);os.chmod(PRIVATE,0o700)
    if not OPLOCK.exists():
        fd=os.open(str(OPLOCK),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);os.close(fd)
    os.chown(OPLOCK,0,0);os.chmod(OPLOCK,0o600)
    if not TOKENFILE.exists():
        atomic_bytes(TOKENFILE,secrets.token_urlsafe(32).encode('ascii'))
    if TOKENFILE.is_symlink():raise RuntimeError('Unsafe token file')
    os.chown(TOKENFILE,0,0);os.chmod(TOKENFILE,0o600)


def atomic_bytes(path,data):
    if path.is_symlink():raise RuntimeError('Unsafe destination symlink')
    temp=path.parent/('.'+path.name+'.'+secrets.token_hex(12))
    fd=os.open(str(temp),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(temp,path)
        df=os.open(str(path.parent),os.O_RDONLY);os.fsync(df);os.close(df)
    finally:
        try:temp.unlink()
        except FileNotFoundError:pass


def write_state(state):atomic_bytes(STATE,json.dumps(state,sort_keys=True).encode())


def requested_cap():
    """Saved user choice is separate from an applied, per-cable cap session."""
    if REQUESTED.is_symlink():raise RuntimeError('Unsafe saved-cap symlink')
    if not REQUESTED.exists():return None
    data=json.loads(REQUESTED.read_text())
    ma=data.get('limit_ma') if isinstance(data,dict) else None
    if type(ma) is not int or not (MIN_MA<=ma<=MAX_MA) or (ma-MIN_MA)%STEP:
        raise RuntimeError('Invalid saved USB current limit')
    return ma


def save_requested_cap(ma):
    atomic_bytes(REQUESTED,json.dumps({'limit_ma':ma},sort_keys=True).encode())


def forget_requested_cap():
    if REQUESTED.is_symlink():raise RuntimeError('Unsafe saved-cap symlink')
    REQUESTED.unlink(missing_ok=True)


def definitely_unplugged(s):
    """Require independent battery and Lightning-port evidence of a disconnect."""
    return (s.get('plugged')==0 and isinstance(s.get('lightning_usb_type'),int)
            and (s.get('lightning_usb_type')==0 or s.get('lightning_usb_power')==0))


def read_state():
    if STATE.is_symlink():raise RuntimeError('Unsafe state file')
    if not STATE.exists():return None
    data=json.loads(STATE.read_text())
    if not isinstance(data,dict) or not isinstance(data.get('session'),str) or not isinstance(data.get('original_max'),(int,type(None))) or not isinstance(data.get('limit_ma'),int):
        raise RuntimeError('Invalid charging state marker')
    return data

@contextlib.contextmanager
def serialized():
    with GUARD:
        fd=os.open(str(OPLOCK),os.O_RDWR|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN)
            os.close(fd)


def note(text):
    try: CORE.append('CONTROL '+text)
    except Exception:pass


def snapshot():
    """Read-only battery sensors and Lightning current-limit registry state."""
    out={'charging':None,'plugged':None,'battery_percent':None,'battery_ma':None,
         'battery_mv':None,'system_mw':None,'system_ma':None,'system_mv':None,
         'adapter_w':None,'usb_ma':None,'usb_base_ma':None,'usb_max_ma':None,'usb_mv':None,
         'lightning_usb_type':None,'lightning_usb_power':None,'lightning_power_ready':None}
    api=CORE.IO()
    bat=api.obtain('AppleSmartBattery')
    if bat:
        try:
            mapping={'charging':'IsCharging','plugged':'ExternalConnected',
                'battery_percent':'CurrentCapacity','battery_ma':'InstantAmperage','battery_mv':'Voltage'}
            for field,key in mapping.items():out[field]=api.field(bat,key)
            out['system_mw']=api.nested(bat,'PowerTelemetryData','SystemPowerIn')
            out['system_ma']=api.nested(bat,'PowerTelemetryData','SystemInputCurrent')
            out['system_mv']=api.nested(bat,'PowerTelemetryData','SystemInputVoltage')
            out['adapter_w']=api.nested(bat,'AdapterDetails','Watts')
        finally:api.release(bat)
    match=api.match(b'IOAccessoryManager')
    if match:
        iterator=__import__('ctypes').c_uint32(0)
        code=api.services(0,match,__import__('ctypes').byref(iterator))
        if code==0:
            best=-1
            try:
                while True:
                    obj=api.iterator_next(iterator.value)
                    if not obj:break
                    try:
                        curr=api.field(obj,'IOAccessoryUSBCurrentLimit')
                        volt=api.field(obj,'IOAccessoryUSBChargingVoltage')
                        active=api.field(obj,'IOAccessoryUSBActive')
                        # Read-only fast connection path. It is a different IOKit
                        # provider from AppleSmartBattery's cached power gauges.
                        # Never infer physically measured mA/W from this registry.
                        namebuf=__import__('ctypes').create_string_buffer(128)
                        if api.service_name(obj,namebuf)==0 and namebuf.value==b'Port-Lightning':
                            out['lightning_usb_type']=api.field(obj,'IOAccessoryUSBConnectType')
                            out['lightning_usb_power']=api.field(obj,'IOAccessoryUSBPower')
                            out['lightning_power_ready']=api.field(obj,'IOAccessoryPowerReady')
                        score=(4 if isinstance(curr,int) and curr>0 else 0)+(2 if isinstance(volt,int) and volt>0 else 0)+(1 if active==1 else 0)
                        if score>best:
                            best=score
                            out['usb_ma']=curr
                            out['usb_base_ma']=api.field(obj,'IOAccessoryUSBCurrentLimitBase')
                            out['usb_max_ma']=api.field(obj,'IOAccessoryUSBCurrentLimitMaximum')
                            out['usb_mv']=volt
                    finally:api.release(obj)
            finally:api.release(iterator.value)
    return out


def _manual_reason(reason):
    return reason in ('manual', 'manual-ui', 'native-app-or-package-removal', 'app-button')


def _refresh_base_current(api, acc, conn, expected_base, reason):
    """Re-announce an already-published charging current and return base control to iOS.

    Never invent an amperage or modify a different USB port. This uses Apple's
    own base-current setter, then its matching restore function, on the same
    verified live Lightning IOAccessoryManager connection.
    """
    base_now=api.field(acc,'IOAccessoryUSBCurrentLimitBase')
    ma=base_now if isinstance(base_now,int) and 500<=base_now<=3000 else None
    if ma is None:
        note(f'BASE REFRESH SKIPPED ({reason}): invalid/absent USB base current {base_now!r}')
        return {'ok':False,'message':'USB cap released, but base current was unavailable; unplug/replug may still be needed.'}
    if isinstance(expected_base,int) and 500<=expected_base<=3000 and ma!=expected_base:
        note(f'BASE REFRESH SKIPPED ({reason}): other driver changed base from {expected_base}mA to {ma}mA')
        return {'ok':False,'message':'USB cap released. Another process changed the base current; no forced refresh performed.'}
    # Refresh the driver's current source using only the same value it already
    # advertises, not a new rate, and immediately hand base ownership back.
    rc=api.setbase(conn,ma)
    note(f'RESTORE BASE REASSERT ({reason}): {ma}mA result=0x{rc & 0xffffffff:08x}')
    if rc!=0:
        return {'ok':False,'message':f'USB cap released, base refresh rejected 0x{rc & 0xffffffff:08x}.'}
    rc2=api.restorebase(conn)
    if rc2!=0:
        note(f'RESTORE BASE RESET ({reason}) failed 0x{rc2 & 0xffffffff:08x}; retrying')
        rc2=api.restorebase(conn)
    note(f'RESTORE BASE RESET ({reason}): result=0x{rc2 & 0xffffffff:08x}; base={api.field(acc,"IOAccessoryUSBCurrentLimitBase")} effective={api.field(acc,"IOAccessoryUSBCurrentLimit")}')
    if rc2!=0:
        return {'ok':False,'message':f'USB cap released but base reset failed 0x{rc2 & 0xffffffff:08x}. Open log.'}
    return {'ok':True,'message':'USB cap cleared; controller base current refreshed (physical charge rate not yet verified).'}


def _power_recover_once(label):
    """Always return BOTH Apple USB power flags to their normal (zero) state.

    Reacquires Port-Lightning WITHOUT requiring it to report actively attached;
    the port can temporarily appear disconnected while power is ignored.
    """
    api=CORE.IO();acc,conn=api.lightning_context_allow_ignored()
    try:
        result1=api.preventsource(conn,0)
        result2=api.powerignore(conn,0)
        note(f'USB SOFT REPLUG RESUME ({label}) preventSource=0x{result1 & 0xffffffff:08x} powerIgnore=0x{result2 & 0xffffffff:08x}')
        return result1==0 and result2==0
    finally:
        api.close(conn);api.release(acc)


def usb_power_watchdog(session):
    # Independent process: survives launchd daemon death, enforces upper bound.
    # The session marker is root-only and only removed after BOTH clears succeed.
    time.sleep(5)
    try:
        if not POWER_MARKER.exists() or POWER_MARKER.is_symlink():return 0
        entry=json.loads(POWER_MARKER.read_text())
        if entry.get('session')!=session:return 0
        for i in range(6):
            try:
                if _power_recover_once('watchdog-'+str(i+1)):
                    POWER_MARKER.unlink(missing_ok=True);return 0
            except Exception as exc:note('USB POWER WATCHDOG recover failed '+repr(exc))
            time.sleep(2)
        note('USB POWER WATCHDOG: unable to clear power-ignore; physically unplug/replug the charging cable')
        return 80
    except Exception as exc:
        note('USB POWER WATCHDOG failed '+repr(exc));return 81


def do_power_restart(reason='native-app'):
    """EXPERIMENTAL: emulate a power-source change, NOT a proven cable detach.

    Apple ioupsd uses SetUSBPreventSourceDetection and SetUSBPowerIgnore
    with 1 in one power state and 0 in the other. We request a 1-second
    off/on transition, log actual input-rail measurements and independently
    recover both flags even after a crash. ONLY explicit native action.
    """
    with serialized():
        state=read_state()
        if state:
            return {'ok':False,'message':'Charging cap still active; no power restart performed.'}
        before=snapshot()
        if before.get('plugged')!=1 or before.get('charging')!=1:
            note('USB SOFT REPLUG skipped: must be charging from Lightning')
            return {'ok':False,'message':'Connect a wired charger and start charging first.'}
        if before.get('usb_max_ma') is not None:
            return {'ok':False,'message':'Another USB maximum remains; software power restart skipped.'}
        api=CORE.IO();acc,conn=api.context()
        session=secrets.token_hex(16)
        armed=False
        try:
            # Declare the recovery obligation BEFORE any hardware write.
            atomic_bytes(POWER_MARKER,json.dumps({'session':session,'time':time.time()}).encode())
            armed=True
            watcher=subprocess.Popen([sys.executable,'-B','-s',str(Path(CORE.__file__).resolve()),'--usb-power-watchdog',session],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)
            note(f'USB SOFT REPLUG START ({reason}): inputW={before.get("system_mw")}mW inputMA={before.get("system_ma")}mA batteryMA={before.get("battery_ma")}mA baselineUSB={before.get("usb_ma")}mA watchdogPID={watcher.pid}')
            # Battery-case system code pairs these flags; no CPU/GPU/thermal write.
            disable_source=api.preventsource(conn,1)
            disable_inflow=api.powerignore(conn,1) if disable_source==0 else -1
            note(f'USB SOFT REPLUG OFF: preventSource=0x{disable_source & 0xffffffff:08x} powerIgnore=0x{disable_inflow & 0xffffffff:08x}')
            if disable_source!=0 or disable_inflow!=0:
                return {'ok':False,'message':'USB power-off command failed; recovery requested.'}
            time.sleep(1.2)
            off=snapshot()
            note(f'USB SOFT REPLUG OFF TELEMETRY: plugged={off.get("plugged")} charging={off.get("charging")} inputMA={off.get("system_ma")} inputW={off.get("system_mw")}')
        except Exception as exc:
            note('USB SOFT REPLUG exception '+repr(exc))
            return {'ok':False,'message':'Software power restart error; recovery requested.'}
        finally:
            try:
                # Primary direct restore of both power flags, using the original
                # port handle in case it is temporarily missing from IOKit.
                ra=api.preventsource(conn,0)
                rb=api.powerignore(conn,0)
                note(f'USB SOFT REPLUG FINALLY ON: prevent=0x{ra & 0xffffffff:08x} ignore=0x{rb & 0xffffffff:08x}')
                cleared=(ra==0 and rb==0)
                if not cleared:
                    try:cleared=_power_recover_once('fallback-new-connection')
                    except Exception as exc:note('USB SOFT REPLUG fallback error '+repr(exc))
                if cleared and armed:POWER_MARKER.unlink(missing_ok=True)
            except Exception as exc:
                note('USB SOFT REPLUG restore exception '+repr(exc))
            api.close(conn);api.release(acc)
        # Keep current limit clear even if Apple automatically updates it.
        after=snapshot()
        note(f'USB SOFT REPLUG AFTER: inputW={after.get("system_mw")}mW inputMA={after.get("system_ma")}mA batteryMA={after.get("battery_ma")}mA USBMax={after.get("usb_max_ma")}')
        threading.Thread(target=_post_restore_audit,args=('soft-replug',),daemon=True).start()
        if POWER_MARKER.exists():
            return {'ok':False,'message':'Power flags could not be confirmed restored. Watchdog running; unplug/replug if charging stays off.'}
        return {'ok':True,'message':'Software off/on command completed; check input rail to verify real charging recovery.'}


def _post_restore_audit(reason):
    """Delayed read-only diagnostics; never report software state as measured wattage."""
    for seconds in (3, 12):
        time.sleep(seconds if seconds==3 else 9)
        try:
            snap=snapshot()
            note(f'RESTORE TELEMETRY +{seconds}s ({reason}): inputW={snap.get("system_mw")}mW inputMA={snap.get("system_ma")}mA batteryMA={snap.get("battery_ma")}mA USBEffectiveMA={snap.get("usb_ma")}mA USBMaxMA={snap.get("usb_max_ma")}mA adapterW={snap.get("adapter_w")}')
        except Exception as err:note('RESTORE TELEMETRY audit error '+repr(err))


def _restore_locked(reason='manual'):
    global _LAST_ERROR
    state=read_state()
    # If v0.8.2 has already cleared its marker but the power path still
    # appears to be stuck, allow the manual button to refresh the currently
    # attached USB *base* without claiming to have removed a different cap.
    if state is None:
        if not _manual_reason(reason):
            note('RESTORE '+reason+': no active current cap')
            return {'ok':True,'message':'No USB maximum override from this tweak.'}
        api=CORE.IO()
        acc,conn=api.context()
        try:
            max_now=api.field(acc,'IOAccessoryUSBCurrentLimitMaximum')
            if max_now is not None:
                note(f'RESTORE NO-MARKER: existing USB maximum {max_now}mA belongs to another owner; leaving unchanged')
                return {'ok':False,'message':f'Other USB maximum {max_now}mA is active; no foreign change made.'}
            note(f'RESTORE NO-MARKER: requesting current-base refresh on attached input; effective={api.field(acc,"IOAccessoryUSBCurrentLimit")} base={api.field(acc,"IOAccessoryUSBCurrentLimitBase")}')
            res=_refresh_base_current(api,acc,conn,None,reason+'-no-marker')
            if res['ok']:
                _LAST_ERROR=''
                threading.Thread(target=_post_restore_audit,args=(reason+'-no-marker',),daemon=True).start()
            else:_LAST_ERROR=res['message']
            return res
        finally:api.close(conn);api.release(acc)
    api=CORE.IO();acc,conn=api.context()
    try:
        current=api.field(acc,'IOAccessoryUSBCurrentLimitMaximum')
        prior=state['original_max']
        desired=state['limit_ma']
        baseline=state.get('original_effective')
        base_before=state.get('original_base')
        effective_before=api.field(acc,'IOAccessoryUSBCurrentLimit')
        note(f'RESTORE START ({reason}): original_effective={baseline}mA original_base={base_before}mA override={current}mA effective={effective_before}mA')
        if current is not None and current!=desired:
            _LAST_ERROR=f'Current override {current}mA differs from our {desired}mA. No unsafe restore applied.'
            note('RESTORE CONFLICT '+_LAST_ERROR)
            return {'ok':False,'message':_LAST_ERROR}
        if CORE.valid_prior(prior):
            rc=api.setmax(conn,prior)
            action=f'reinstated original {prior}mA override'
        else:
            # First explicitly raise the SAME maximum limit we used for
            # restriction. Clearing alone visibly changed IORegistry on XS
            # Max without immediately returning actual input power.
            if isinstance(baseline,int) and desired<baseline<=3000:
                r1=api.setmax(conn,baseline)
                note(f'RESTORE RAISE MAX ({reason}): {desired} -> {baseline}mA return=0x{r1 & 0xffffffff:08x}')
                if r1==0:time.sleep(0.14)
            rc=api.clearmax(conn)
            action='cleared USB maximum override after raising it to original safe limit'
        note(f'RESTORE MAX ({reason}): {action}; result=0x{rc & 0xffffffff:08x}; effective={api.field(acc,"IOAccessoryUSBCurrentLimit")} max={api.field(acc,"IOAccessoryUSBCurrentLimitMaximum")}')
        if rc!=0:
            _LAST_ERROR=f'USB maximum restore failed 0x{rc & 0xffffffff:08x}'
            return {'ok':False,'message':_LAST_ERROR}
        observed=api.field(acc,'IOAccessoryUSBCurrentLimitMaximum')
        if observed==desired and prior!=desired:
            _LAST_ERROR='Restore command accepted but our current cap still reads active; retry.'
            note('RESTORE PENDING '+_LAST_ERROR)
            return {'ok':False,'message':_LAST_ERROR}
        # Our USB maximum has now been lifted. Remove the marker even if
        # recalculation fails, to avoid falsely claiming the cap is enabled.
        STATE.unlink(missing_ok=True)
        base_result={'ok':True,'message':'Original USB maximum restored.'}
        if not CORE.valid_prior(prior) and _manual_reason(reason):
            base_result=_refresh_base_current(api,acc,conn,base_before,reason)
        _LAST_ERROR='' if base_result['ok'] else base_result['message']
        note(f'RESTORE END ({reason}): effective={api.field(acc,"IOAccessoryUSBCurrentLimit")} max={api.field(acc,"IOAccessoryUSBCurrentLimitMaximum")} base={api.field(acc,"IOAccessoryUSBCurrentLimitBase")} outcome={base_result["message"]}')
        if base_result['ok']:
            threading.Thread(target=_post_restore_audit,args=(reason,),daemon=True).start()
        return base_result
    finally:api.close(conn);api.release(acc)


def do_restore(reason='manual'):
    global _LAST_ERROR
    with serialized():
        if _manual_reason(reason):
            # Restore/disable is the ONLY user action which forgets the setting.
            forget_requested_cap()
            # A physical disconnect releases the cable session. Never require a
            # charger just to disable the saved cap while unplugged.
            s=snapshot()
            if s.get('plugged')==0:
                state=read_state()
                if state is None or (definitely_unplugged(s) and s.get('usb_max_ma') is None):
                    if state is not None:STATE.unlink(missing_ok=True)
                    _LAST_ERROR=''
                    return {'ok':True,'message':'Saved current cap disabled; normal charging next connection.'}
        return _restore_locked(reason)


def do_enable(limit,remember=True):
    global _LAST_ERROR
    try:ma=int(limit)
    except (TypeError,ValueError):return {'ok':False,'message':'Invalid current limit'}
    if ma<MIN_MA or ma>MAX_MA or (ma-MIN_MA)%STEP!=0:return {'ok':False,'message':'Choose 500–2400mA in 100mA steps'}
    with serialized():
        # If Restore won the race against an automatic monitor iteration,
        # never reapply a cap which the user has just removed.
        if not remember and requested_cap()!=ma:
            return {'ok':False,'message':'Saved cap changed; stale automatic apply cancelled.'}
        state=read_state()
        if state is not None:
            restored=_restore_locked('switch-limit')
            if not restored['ok']:return restored
        api=CORE.IO();acc,conn=api.context()
        try:
            sensor=api.read(acc)
            note('ENABLE baseline '+CORE.fmt(sensor))
            if sensor.get('IsCharging')!=1 or sensor.get('ExternalConnected')!=1:
                return {'ok':False,'message':'Plug into a charger and wait until Charging: Yes.'}
            active=sensor.get('IOAccessoryUSBCurrentLimit')
            if not isinstance(active,int) or active<MIN_MA:
                return {'ok':False,'message':'USB input-current limit is unreadable; no change made.'}
            prior=sensor.get('IOAccessoryUSBCurrentLimitMaximum')
            if isinstance(prior,int) and prior<ma:
                return {'ok':False,'message':f'Another {prior}mA maximum is already active. Refusing to raise it.'}
            if ma>=active:
                return {'ok':False,'message':f'USB input currently limited to {active}mA. Choose below that.'}
            token=secrets.token_hex(16)
            state={'session':token,'limit_ma':ma,'original_max':prior if CORE.valid_prior(prior) else None,
                'original_effective':active,'original_base':sensor.get('IOAccessoryUSBCurrentLimitBase'),
                'created_epoch':time.time()}
            # Start independent crash watchdog BEFORE hardware write. This avoids
            # a crash window after applying the limit but before launching failsafe.
            write_state(state)
            try:
                p=subprocess.Popen([sys.executable,'-B','-s',str(Path(CORE.__file__).resolve()),'--panel-watchdog',token,str(os.getpid())],
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)
                note('FAILSAFE armed pid='+str(p.pid)+' before current-limit write')
            except Exception as exc:
                STATE.unlink(missing_ok=True)
                _LAST_ERROR='Cannot arm independent watchdog; no charging change attempted: '+str(exc)
                return {'ok':False,'message':_LAST_ERROR}
            rc=api.setmax(conn,ma)
            note(f'ENABLE requested={ma}mA original={active}mA response=0x{rc & 0xffffffff:08x}')
            if rc!=0:
                STATE.unlink(missing_ok=True)
                return {'ok':False,'message':f'Controller rejected limit: 0x{rc & 0xffffffff:08x}'}
            # USB controller on XS Max updated current-limit registry on the first 1s poll.
            time.sleep(0.7)
            observed=api.field(acc,'IOAccessoryUSBCurrentLimitMaximum')
            effective=api.field(acc,'IOAccessoryUSBCurrentLimit')
            if observed!=ma or (isinstance(effective,int) and effective>ma):
                note(f'ENABLE readback mismatch max={observed} effective={effective}; restoring immediately')
                r=_restore_locked('readback-mismatch')
                _LAST_ERROR=f'Controller did not verify the {ma}mA cap. Restore: {r["message"]}'
                return {'ok':False,'message':_LAST_ERROR}
            note(f'ENABLE confirmed USB maximum {observed}mA; no CPU/GPU/thermal adjustments')
            if remember:
                # Only persist a cap after the controller has confirmed it.
                try:save_requested_cap(ma)
                except Exception as err:
                    note('SAVE CAP FAILED '+repr(err)+'; restoring hardware')
                    recovery=_restore_locked('save-failed')
                    return {'ok':False,'message':'Could not remember current cap: '+str(err)+'; restore: '+recovery['message']}
            _LAST_ERROR=''
            return {'ok':True,'message':f'{ma}mA cap applied (software-reported).'}
        finally:api.close(conn);api.release(acc)


def status_payload():
    try:
        s=snapshot()
    except Exception as exc:
        s={'error':'Read-only sensors unavailable: '+str(exc)}
    state=read_state()
    wanted=requested_cap()
    # The toggle reflects the *saved* choice, even between cable connections.
    s['enabled']=wanted is not None or state is not None
    s['selected_ma']=wanted if wanted is not None else (state['limit_ma'] if state else 1500)
    # The Lightning registry updates before Apple's battery-power telemetry.
    # Detect cable presence directly, but never manufacture mA or W readings.
    usb_type=s.get('lightning_usb_type')
    usb_power=s.get('lightning_usb_power')
    wired_connected=(isinstance(usb_type,int) and usb_type>0 and usb_power==1)
    s['lightning_connected']=wired_connected
    power_ready=(s.get('plugged')==1 and s.get('charging')==1 and
                 isinstance(s.get('system_mw'),int) and s['system_mw']>0 and
                 isinstance(s.get('system_ma'),int) and s['system_ma']>0)
    s['power_readings_pending']=bool(wired_connected and not power_ready)
    # Preserve actual errors over informational status text.
    # A cap is confirmed by the USB controller's own IOKit maximum, not the
    # AppleSmartBattery rate gauges, which can lag by 15–20+ seconds.
    # Keep active confirmation distinct from unrefreshed W/mA telemetry.
    selected=state['limit_ma'] if state else None
    max_seen=s.get('usb_max_ma')
    effective=s.get('usb_ma')
    verified_cap=(state is not None and isinstance(max_seen,int) and
                  max_seen==selected and isinstance(effective,int) and
                  effective<=selected)
    s['cap_controller_verified']=bool(verified_cap)
    # Recent cap notices are time-bounded information, not a physical watt
    # convergence assertion. The permanent disclaimer lives inside the UI.
    cap_age=time.time()-state.get('created_epoch',0) if state else -1
    if _LAST_ERROR:
        s['message']=_LAST_ERROR
    elif definitely_unplugged(s):
        s['message']='Charger Disconnected'
    elif verified_cap and 0<=cap_age<25:
        s['message']=f'{selected}mA cap applied — live power readings may be delayed'
    elif verified_cap:
        s['message']=f'{selected}mA USB cap active'
    elif state and wired_connected:
        s['message']='Cap state exists — waiting for USB controller confirmation'
    elif s['power_readings_pending']:
        s['message']='Charger Connected — Waiting for Power Readings'
    elif s.get('lightning_usb_type') is not None and not wired_connected:
        s['message']='Charger Disconnected'
    else:
        s['message']=''
    s['timestamp']=time.time()
    if isinstance(s.get('usb_mv'),int) and isinstance(s.get('usb_ma'),int):
        s['usb_est_w']=round(s['usb_mv']*s['usb_ma']/1000000,2)
    return s


def monitor_once():
    """Reconcile the saved preference with the currently connected USB input."""
    wanted=requested_cap()
    state=read_state()
    if wanted is None and state is None:return
    s=snapshot()

    if wanted is None:
        # Compatibility with any legacy active session that has no saved choice.
        if state and (s.get('plugged')==0 or s.get('charging')==0):
            note('AUTO RESTORE: charging inactive and no saved cap')
            do_restore('auto-disconnect')
        elif state and s.get('usb_max_ma') is not None and s['usb_max_ma']!=state['limit_ma']:
            note('NOTICE: USB maximum changed externally; dropping stale session')
            with serialized():
                current=read_state()
                if current and current.get('session')==state['session']:
                    STATE.unlink(missing_ok=True)
        return

    if definitely_unplugged(s):
        # On a genuine unplug, forget only the hardware-session marker once
        # the old maximum has disappeared. The user's choice remains saved.
        if state and s.get('usb_max_ma') is None:
            with serialized():
                current=read_state()
                if current and current.get('session')==state['session']:
                    STATE.unlink(missing_ok=True)
                    note(f'UNPLUGGED: retained saved {wanted}mA cap for next connection')
        return

    # Do not touch the USB controller while disconnected, idle, or still
    # negotiating a fresh Lightning charging connection.
    if s.get('plugged')!=1 or s.get('charging')!=1:return
    if state:
        if state['limit_ma']==wanted and s.get('usb_max_ma')==wanted:
            return  # Already active: do not pulse the controller on each poll.
        if s.get('usb_max_ma') not in (None,state['limit_ma']):
            # An outside limit took ownership; never overwrite that owner.
            note('AUTO CAP: a different USB maximum is present; not overwriting')
            with serialized():
                current=read_state()
                if current and current.get('session')==state['session']:
                    STATE.unlink(missing_ok=True)
            return
    elif s.get('usb_max_ma') is not None:
        # Without our active marker, a pre-existing limit is not ours.
        return

    result=do_enable(wanted,remember=False)
    if result['ok']:
        note(f'AUTO APPLY: restored saved {wanted}mA cap after charging reconnection')
    else:
        note(f'AUTO APPLY PENDING: {result["message"]}')


def monitor_loop():
    while True:
        time.sleep(PING_INTERVAL)
        try:monitor_once()
        except Exception as err:
            note('MONITOR warning: '+repr(err))

def boot_recover():
    # Fail-safe: never silently resume an override across daemon restart/re-jailbreak.
    try:
        if read_state():
            note('DAEMON RESTART: previously active cap detected; restoring before accepting commands')
            res=do_restore('daemon-restart')
            if not res['ok']:note('DAEMON RESTART RESTORE NEEDS ATTENTION '+res['message'])
    except Exception as e:note('STARTUP RESTORE ERROR '+repr(e))


def watchdog(session,parent_pid):
    # Own process. Even if the web UI disappears, the root daemon remains.
    # If root daemon unexpectedly dies, restore within ~5 seconds.
    for _ in range(24*3600//5):
        time.sleep(5)
        try:
            state=read_state()
            if not state or state.get('session')!=session:return 0
            try:os.kill(int(parent_pid),0);alive=True
            except ProcessLookupError:alive=False
            except PermissionError:alive=True
            if alive:continue
            note('FAILSAFE: root daemon no longer alive; restoring USB current maximum')
            for attempt in range(5):
                try:
                    result=do_restore('daemon-crash-watchdog')
                    if result['ok']:return 0
                except Exception as e:note('FAILSAFE restore attempt failed: '+repr(e))
                time.sleep(3)
            return 51
        except Exception as e:note('FAILSAFE error '+repr(e));return 52
    return 53


class Handler(http.server.BaseHTTPRequestHandler):
    server_version='551UK-USB/0.8.0';sys_version=''
    def log_message(self,*args):pass
    def _allowed_host(self):
        host=self.headers.get('Host','')
        return host in (f'{HOST}:{PORT}',f'localhost:{PORT}')
    def _send(self,body,ctype='application/json',code=200):
        self.send_response(code)
        self.send_header('Content-Type',ctype)
        self.send_header('Cache-Control','no-store, max-age=0')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def _json(self,data,code=200):self._send(json.dumps(data).encode('utf-8'),'application/json; charset=utf-8',code)
    def do_GET(self):
        if not self._allowed_host():return self._json({'error':'bad host'},403)
        path=self.path.split('?')[0]
        if path in ('/','/index.html'):
            try:
                doc=UIHTML.read_text().replace('##CSRF##',TOKENFILE.read_text().strip())
                self._send(doc.encode(),'text/html; charset=utf-8')
            except Exception as e:self._json({'error':str(e)},500)
        elif path=='/api/status':
            try:self._json(status_payload())
            except Exception as e:self._json({'error':str(e)},500)
        elif path=='/api/log':
            try:
                # Show last 45KiB, avoid shipping huge logs over HTTP.
                content=LOGFILE.read_bytes()[-46080:].decode('utf-8','replace') if LOGFILE.exists() else 'No log yet.'
                self._json({'log':content})
            except Exception as e:self._json({'error':str(e)},500)
        elif path in ('/apple-touch-icon.png','/icon.png'):
            try:self._send(ICON.read_bytes(),'image/png')
            except Exception:self._json({'error':'icon unavailable'},404)
        else:self._json({'error':'unknown route'},404)
    def do_POST(self):
        if not self._allowed_host():return self._json({'error':'bad host'},403)
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://{HOST}:{PORT}',f'http://localhost:{PORT}'):
            return self._json({'error':'foreign origin blocked'},403)
        if self.headers.get('X-CSRF-Token')!=TOKENFILE.read_text().strip():
            return self._json({'error':'authorisation token missing'},403)
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self._json({'error':'expected JSON'},415)
        try:n=int(self.headers.get('Content-Length','0'))
        except Exception:n=0
        if n<1 or n>1024:return self._json({'error':'invalid request length'},413)
        try:arg=json.loads(self.rfile.read(n))
        except Exception:return self._json({'error':'invalid JSON'},400)
        if not isinstance(arg,dict):return self._json({'error':'invalid payload'},400)
        try:
            if self.path=='/api/enable' and set(arg)=={'ma'}:r=do_enable(arg['ma'])
            elif self.path=='/api/restore' and not arg:r=do_restore('manual-ui')
            else:r={'ok':False,'message':'unknown action'}
            self._json(r,200 if r['ok'] else 409)
        except Exception as e:
            note('WEB ACTION ERROR '+repr(e))
            self._json({'ok':False,'message':str(e)},500)


def serve_panel():
    class S(http.server.ThreadingHTTPServer):daemon_threads=True;allow_reuse_address=True
    server=S((HOST,PORT),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True,name='USBCurrentApp')
    thread.start()
    note('CONTROL PANEL READY http://127.0.0.1:%d'%PORT)
    monitor=threading.Thread(target=monitor_loop,daemon=True,name='USBCurrentMonitor')
    monitor.start()
    return server
