#!/var/jb/usr/bin/python3
"""551UK USB input-current experiment AND continuous control panel (iOS 16 Dopamine).

The daemon is started as root by launchd. It accepts only PROBE, TEST and RESTORE
from local uid=501 (mobile) or uid=0 over a mode-0600 Unix socket. TEST calls
Apple's private IOAccessoryManagerSetUSBCurrentLimitMaximum(500) for 8 seconds,
then clears that test cap or restores the previous USB max-current limit.
No CPU/GPU, thermal, charge percentage, or AppleChargeRateLimitIndex writes.
"""
import ctypes as C
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import usb_control_panel as control_panel
BASE=Path('/var/jb/var/mobile/551UK-ChargeRateTest-v052')
SOCK=BASE/'chargerated.sock'
LOG=BASE/'charging-test.txt'
BOOTS=BASE/'daemon-status.txt'
MARKER=BASE/'usbcurrent-watchdog.json'
LIMIT_MA=500
TEST_SECONDS=8
WATCHDOG_SECONDS=22


def append(message, dest=LOG):
    try:
        fd=os.open(str(dest),os.O_WRONLY|os.O_CREAT|os.O_APPEND|getattr(os,'O_NOFOLLOW',0),0o600)
        # The GUI runs as mobile (uid 501). A root-started daemon must NEVER
        # leave the shared log root-owned or the app falls back to private tmp.
        if dest == LOG and os.geteuid() == 0:
            os.fchown(fd,501,501)
            os.fchmod(fd,0o600)
        with os.fdopen(fd,'a',encoding='utf-8') as stream:
            stream.write(time.strftime('%Y-%m-%dT%H:%M:%S%z ') + message.replace('\n',' ')+'\n')
            stream.flush()
    except Exception:
        # Failure to write the main test log must abort before any hardware write.
        if dest == LOG: raise


def load_dll(path):
    return C.CDLL(path)


class IO:
    def __init__(self):
        self.kit=load_dll('/System/Library/Frameworks/IOKit.framework/IOKit')
        self.cf=load_dll('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.accessory=load_dll('/usr/lib/libIOAccessoryManager.dylib')
        self.libsystem=load_dll('/usr/lib/libSystem.B.dylib')
        def sig(lib,name,restype,args):
            fn=getattr(lib,name);fn.restype=restype;fn.argtypes=args;return fn
        U=C.c_uint32;P=C.c_void_p
        self.match=sig(self.kit,'IOServiceMatching',P,[C.c_char_p])
        self.service=sig(self.kit,'IOServiceGetMatchingService',U,[U,P])
        self.services=sig(self.kit,'IOServiceGetMatchingServices',C.c_int,[U,P,C.POINTER(U)])
        self.iterator_next=sig(self.kit,'IOIteratorNext',U,[U])
        self.service_name=sig(self.kit,'IORegistryEntryGetName',C.c_int,[U,C.c_void_p])
        self.properties=sig(self.kit,'IORegistryEntryCreateCFProperties',C.c_int,[U,C.POINTER(P),P,U])
        self.open=sig(self.kit,'IOServiceOpen',C.c_int,[U,U,U,C.POINTER(U)])
        self.close=sig(self.kit,'IOServiceClose',C.c_int,[U])
        self.release=sig(self.kit,'IOObjectRelease',C.c_int,[U])
        self.prop=sig(self.kit,'IORegistryEntryCreateCFProperty',P,[U,P,P,U])
        self.cs=sig(self.cf,'CFStringCreateWithCString',P,[P,C.c_char_p,U])
        self.cfrelease=sig(self.cf,'CFRelease',None,[P])
        self.type=sig(self.cf,'CFGetTypeID',C.c_ulong,[P])
        self.ntype=sig(self.cf,'CFNumberGetTypeID',C.c_ulong,[])
        self.btype=sig(self.cf,'CFBooleanGetTypeID',C.c_ulong,[])
        self.dtype=sig(self.cf,'CFDictionaryGetTypeID',C.c_ulong,[])
        self.number=sig(self.cf,'CFNumberGetValue',C.c_ubyte,[P,C.c_int,P])
        self.boolval=sig(self.cf,'CFBooleanGetValue',C.c_ubyte,[P])
        self.dictval=sig(self.cf,'CFDictionaryGetValue',P,[P,P])
        self.dictcount=sig(self.cf,'CFDictionaryGetCount',C.c_long,[P])
        self.dictkeys=sig(self.cf,'CFDictionaryGetKeysAndValues',None,[P,C.POINTER(P),C.POINTER(P)])
        self.stringtype=sig(self.cf,'CFStringGetTypeID',C.c_ulong,[])
        self.string_get=sig(self.cf,'CFStringGetCString',C.c_ubyte,[P,C.c_void_p,C.c_long,U])
        self.setmax=sig(self.accessory,'IOAccessoryManagerSetUSBCurrentLimitMaximum',C.c_int,[U,C.c_uint64])
        self.clearmax=sig(self.accessory,'IOAccessoryManagerClearUSBCurrentLimitMaximum',C.c_int,[U])
        self.setbase=sig(self.accessory,'IOAccessoryManagerSetUSBCurrentLimitBase',C.c_int,[U,C.c_uint64])
        self.restorebase=sig(self.accessory,'IOAccessoryManagerRestoreUSBCurrentLimitBase',C.c_int,[U])
        self.powerignore=sig(self.accessory,'IOAccessoryManagerSetUSBPowerIgnore',C.c_int,[U,U])
        self.preventsource=sig(self.accessory,'IOAccessoryManagerSetUSBPreventSourceDetection',C.c_int,[U,U])
        self.taskport=U.in_dll(self.libsystem,'mach_task_self_').value

    def obtain(self,name):
        match=self.match(name.encode())
        if not match: return 0
        return self.service(0,match)

    def rawnum(self,value):
        if not value:return None
        ty=self.type(value)
        if ty==self.ntype():
            n=C.c_longlong(-1)
            if self.number(value,4,C.byref(n)):return n.value
        if ty==self.btype():return int(self.boolval(value))
        return None

    def key(self,key):return self.cs(None,key.encode(),0x08000100)
    def field(self,obj,key):
        k=self.key(key)
        if not k:return None
        try: v=self.prop(obj,k,None,0)
        finally:self.cfrelease(k)
        if not v:return None
        try:return self.rawnum(v)
        finally:self.cfrelease(v)

    def nested(self,obj,parent,key):
        k=self.key(parent)
        if not k:return None
        try: v=self.prop(obj,k,None,0)
        finally:self.cfrelease(k)
        if not v:return None
        try:
            if self.type(v)!=self.dtype():return None
            k2=self.key(key)
            if not k2:return None
            try:return self.rawnum(self.dictval(v,k2))
            finally:self.cfrelease(k2)
        finally:self.cfrelease(v)

    def registry_info(self,obj):
        """Read-only inspection of IOKit properties for diagnostic display."""
        nm=C.create_string_buffer(128)
        name='unknown'
        try:
            if self.service_name(obj,nm)==0:name=nm.value.decode('utf-8','replace')
        except Exception:pass
        props=C.c_void_p()
        try:
            rc=self.properties(obj,C.byref(props),None,0)
            if rc!=0 or not props.value:
                return name,f'properties result=0x{rc & 0xffffffff:08x}'
            count=int(self.dictcount(props))
            if count<0 or count>512:return name,f'properties count abnormal={count}'
            keys=(C.c_void_p*max(count,1))()
            values=(C.c_void_p*max(count,1))()
            self.dictkeys(props,keys,values)
            strings=[]
            for k in keys[:count]:
                if not k or self.type(k)!=self.stringtype():continue
                b=C.create_string_buffer(160)
                if self.string_get(k,b,160,0x08000100):strings.append(b.value.decode('utf-8','replace'))
            return name,'properties count=%d names=%s'%(count,','.join(sorted(strings)[:75]))
        except Exception as err:
            return name,f'property-enumeration error={type(err).__name__}:{err}'
        finally:
            if props.value:self.cfrelease(props)

    def context(self):
        # XS Max has AT LEAST TWO IOAccessoryManager services: published
        # diagnostics show port 512 detached, port 1 USB-connected. The previous
        # IOServiceGetMatchingService used only the FIRST instance. Never write
        # to that instance without checking attachment / USB current properties.
        match=self.match(b'IOAccessoryManager')
        if not match:raise RuntimeError('IOAccessoryManager matching dictionary unavailable')
        iterator=C.c_uint32(0)
        rc=self.services(0,match,C.byref(iterator))
        if rc!=0:raise RuntimeError(f'IOServiceGetMatchingServices failed 0x{rc & 0xffffffff:08x}')
        candidates=[]
        try:
            while True:
                obj=self.iterator_next(iterator.value)
                if not obj:break
                vals={name:self.field(obj,name) for name in (
                    'IOAccessoryUSBCurrentLimit','IOAccessoryUSBCurrentLimitBase',
                    'IOAccessoryUSBCurrentLimitMaximum','IOAccessoryUSBCurrentLimitOffset',
                    'IOAccessoryUSBChargingVoltage','IOAccessoryUSBActive',
                    'IOAccessoryUSBConnectType','IOAccessoryUSBConnectTypePublished',
                    'IOAccessoryUSBPower','IOAccessoryPowerReady',
                    'IOAccessoryManagerPort','IOAccessoryManagerPrimaryPort',
                    'IOAccessoryManagerType')}
                current=vals['IOAccessoryUSBCurrentLimit']
                voltage=vals['IOAccessoryUSBChargingVoltage']
                active=vals['IOAccessoryUSBActive']
                # Require verifiable attached USB input. Merely having a registry
                # service or a successful userclient connection isn't sufficient.
                viable=(isinstance(current,int) and current>0) or (
                    isinstance(voltage,int) and voltage>0 and active==1)
                score=(4 if isinstance(current,int) and current>0 else 0) + (
                    2 if isinstance(voltage,int) and voltage>0 else 0) + (1 if active==1 else 0)
                name,registry=self.registry_info(obj)
                append('USB PORT CANDIDATE '+str(len(candidates)+1)+' name='+name+' '+fmt(vals)+' attached='+str(viable)+' score='+str(score))
                append('USB PORT REGISTRY '+str(len(candidates)+1)+' '+registry)
                candidates.append((score,viable,obj))
        finally:
            if iterator.value:self.release(iterator.value)
        if not candidates:
            raise RuntimeError('no IOAccessoryManager services found')
        candidates.sort(key=lambda p:p[0],reverse=True)
        selected=None
        conn=C.c_uint32(0)
        for score,viable,obj in candidates:
            if not viable:continue
            c=C.c_uint32(0)
            rc=self.open(obj,self.taskport,0,C.byref(c))
            append(f'USB PORT OPEN attached score={score} result=0x{rc & 0xffffffff:08x} connection={bool(c.value)}')
            if rc==0 and c.value:
                selected=obj;conn=c
                break
        for _,_,obj in candidates:
            if obj!=selected:self.release(obj)
        if selected is None:
            append('USB DIAGNOSTIC RESULT: no verified openable attached USB input-current controller; 500mA WRITE SKIPPED, charging left unchanged')
            raise RuntimeError('no attached IOAccessoryManager has a usable, openable USB input-current path; refusing write')
        append('USB PORT SELECTED: attached manager with readable USB current or active USB voltage')
        return selected,conn.value

    def lightning_context_allow_ignored(self):
        """Open the actual Lightning accessory port even if ignore disables its status.

        This intentionally bypasses context()'s charging-attached requirement ONLY
        for restoring USBPowerIgnore=0 / PreventSourceDetection=0.
        """
        match=self.match(b'IOAccessoryManager')
        if not match:raise RuntimeError('IOAccessoryManager unavailable')
        iterator=C.c_uint32(0)
        rc=self.services(0,match,C.byref(iterator))
        if rc:raise RuntimeError(f'IOServiceGetMatchingServices 0x{rc & 0xffffffff:08x}')
        found=None;conn=C.c_uint32(0)
        try:
            while True:
                obj=self.iterator_next(iterator.value)
                if not obj:break
                name,_=self.registry_info(obj)
                if name!='Port-Lightning':
                    self.release(obj);continue
                opened=self.open(obj,self.taskport,0,C.byref(conn))
                if opened==0 and conn.value:
                    found=obj;break
                self.release(obj)
        finally:
            if iterator.value:self.release(iterator.value)
        if found is None:raise RuntimeError('Port-Lightning not openable for power restore')
        return found,conn.value

    def read(self,acc):
        result={key:self.field(acc,key) for key in ('IOAccessoryUSBCurrentLimit',
            'IOAccessoryUSBCurrentLimitBase','IOAccessoryUSBCurrentLimitOffset',
            'IOAccessoryUSBCurrentLimitMaximum','IOAccessoryUSBChargingVoltage')}
        bat=self.obtain('AppleSmartBattery')
        if bat:
            try:
                result.update({key:self.field(bat,key) for key in ('CurrentCapacity','ExternalConnected','IsCharging','InstantAmperage','Voltage','AppleChargeRateLimitIndex')})
                result['SystemPowerIn_mW']=self.nested(bat,'PowerTelemetryData','SystemPowerIn')
                result['SystemInputCurrent_mA']=self.nested(bat,'PowerTelemetryData','SystemInputCurrent')
                result['SystemInputVoltage_mV']=self.nested(bat,'PowerTelemetryData','SystemInputVoltage')
                result['AdapterWatts']=self.nested(bat,'AdapterDetails','Watts')
            finally:self.release(bat)
        return result


def fmt(sample):
    return ' '.join(f'{k}={v if v is not None else "N/A"}' for k,v in sample.items())


def valid_prior(n):
    return isinstance(n,int) and 100<=n<=3000


def restore_context(api,conn,old):
    if valid_prior(old):
        return api.setmax(conn,old),f'restored previous maximum {old}mA'
    return api.clearmax(conn),'cleared test maximum'


def get_marker():
    if MARKER.is_symlink():raise RuntimeError('unsafe watchdog marker is symlink')
    if not MARKER.exists():return None
    with MARKER.open('r',encoding='utf-8') as f:return json.load(f)


def marker_write(obj):
    # Do not overwrite existing lock; this guards against overlapping tests.
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(str(MARKER),flags,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:
        json.dump(obj,f);f.flush();os.fsync(f.fileno())


def cleanup_marker(token):
    marker=get_marker()
    if marker and marker.get('token')==token:MARKER.unlink()


def current_restoration(reason,force=False):
    marker=get_marker()
    if not marker and not force:
        append(f'RESTORE ({reason}): no active test marker, no hardware write needed')
        return 0
    # With no marker we only clear the test cap when explicitly asked.
    previous=marker.get('previous_max') if marker else None
    api=IO();acc,conn=api.context()
    try:
        rc,description=restore_context(api,conn,previous)
        append(f'RESTORE ({reason}): {description}; API result=0x{rc & 0xffffffff:08x}; {fmt(api.read(acc))}')
    finally:api.close(conn);api.release(acc)
    if rc==0 and marker:cleanup_marker(marker.get('token'))
    return 0 if rc==0 else 45


def watchdog(token):
    time.sleep(WATCHDOG_SECONDS)
    try:
        marker=get_marker()
        if not marker or marker.get('token')!=token:return 0
        append('WATCHDOG: test marker remains after timeout, attempting restore')
        # On failure, retry but never reapply a current cap.
        for attempt in range(4):
            code=current_restoration(f'watchdog_attempt_{attempt+1}')
            if code==0:return 0
            time.sleep(5)
        append('WATCHDOG ERROR: USB max could not be restored; unplug charger and use Restore button')
        return 50
    except Exception as err:
        try:append(f'WATCHDOG exception: {type(err).__name__}: {err}')
        except Exception:pass
        return 51


def run_test():
    # The old native app is diagnostic-only while the browser panel owns a
    # persistent cap. Never let a short test trample its user's setting.
    if control_panel and control_panel.read_state():
        append('TEST REFUSED: persistent current cap enabled in Charge Control; disable it first')
        return 46
    # The daemon handles one request at a time, no async write from the GUI.
    try:
        stale=get_marker()
        if stale:
            append('PRIOR TEST MARKER: attempting restoration before next test')
            code=current_restoration('stale-marker')
            if code!=0:return 40
        api=IO();acc,conn=api.context()
    except Exception as e:
        append(f'TEST refused before change: {type(e).__name__}: {e}')
        return 41
    try:
        baseline=api.read(acc)
        append('TEST START v0.7.4 uid=%s euid=%s limit=%dmA seconds=%d; no index/thermal/CPU/GPU changes'%(os.getuid(),os.geteuid(),LIMIT_MA,TEST_SECONDS))
        append('BEFORE '+fmt(baseline))
        if baseline.get('ExternalConnected') != 1 or baseline.get('IsCharging') != 1:
            append('TEST REFUSED: phone must be actively charging; no change made')
            return 42
        present=baseline.get('IOAccessoryUSBCurrentLimit')
        if present is None:
            append('INFO: current USB limit not readable; will still attempt a bounded safe test')
        elif present<=LIMIT_MA:
            append('TEST REFUSED: existing current limit is already <=500mA, reduction cannot be measured')
            return 43
        previous=baseline.get('IOAccessoryUSBCurrentLimitMaximum')
        token=uuid.uuid4().hex
        marker_write({'token':token,'previous_max':previous,'created_epoch':time.time(),'test_mA':LIMIT_MA})
        watchdog_proc=None
        try:
            # Background repair remains alive even if main daemon is killed.
            watchdog_proc=subprocess.Popen([sys.executable,'-B','-s',str(Path(__file__).resolve()),'--watchdog',token],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)
            append('WATCHDOG spawned pid=%s timeout=%ss'%(watchdog_proc.pid,WATCHDOG_SECONDS))
            rc=api.setmax(conn,LIMIT_MA)
            append(f'SET USB maximum {LIMIT_MA}mA: result=0x{rc & 0xffffffff:08x} (success does NOT prove physical wattage changed)')
            if rc!=0:
                cleanup_marker(token)
                return 44
            for t in range(TEST_SECONDS):
                time.sleep(1)
                append(f'DURING t={t+1}s '+fmt(api.read(acc)))
        finally:
            # Restore regardless of application errors, using same known-good port.
            marker=get_marker()
            if marker and marker.get('token')==token:
                for attempt in range(3):
                    rc,desc=restore_context(api,conn,previous)
                    append(f'FINALLY RESTORE attempt={attempt+1}: {desc} result=0x{rc & 0xffffffff:08x}')
                    if rc==0:
                        cleanup_marker(token)
                        break
                    time.sleep(2)
                if rc!=0:
                    append('WARNING: immediate restoration failed, independent watchdog will retry. Unplug charger now.')
                    return 45
        time.sleep(1)
        append('AFTER '+fmt(api.read(acc)))
        append('TEST END: USB input max test complete; compare with USB wattmeter for true external watts')
        return 0
    except Exception as e:
        append(f'TEST ERROR: {type(e).__name__}: {e}')
        return 46
    finally:
        api.close(conn);api.release(acc)


def peer_identity(conn):
    """Obtain the peer's *kernel-authenticated* Darwin uid/gid.

    Procursus Python on some iOS builds omits socket.getpeereid(), although
    libSystem exports getpeereid(2). Never infer identity from socket pathname
    or permit an unauthenticated connection.
    """
    if hasattr(conn, 'getpeereid'):
        return conn.getpeereid()
    libsystem=C.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True)
    fn=libsystem.getpeereid
    fn.argtypes=[C.c_int,C.POINTER(C.c_uint32),C.POINTER(C.c_uint32)]
    fn.restype=C.c_int
    uid=C.c_uint32(0xffffffff)
    gid=C.c_uint32(0xffffffff)
    if fn(conn.fileno(),C.byref(uid),C.byref(gid)) != 0:
        err=C.get_errno()
        raise OSError(err, f'getpeereid failed errno={err}')
    return uid.value,gid.value


def serve():
    if os.geteuid()!=0:
        raise RuntimeError(f'launchd did not start root euid={os.geteuid()}')
    BASE.mkdir(mode=0o700,parents=True,exist_ok=True)
    if BASE.is_symlink():raise RuntimeError('unsafe symlink log directory')
    # Diagnostic failures are recorded in the same log visible in the GUI.
    append(f'USB current daemon 0.8.4 boot: uid={os.getuid()} euid={os.geteuid()} python={sys.version.split()[0]}')
    try:
        libs=IO()
        svc=libs.obtain('IOAccessoryManager')
        append(f'DAEMON availability IOAccessoryManager={svc}; wired current control exported=YES')
        if svc:libs.release(svc)
    except Exception as e:
        append(f'DAEMON availability probe failed: {type(e).__name__}: {e}')
    # Persistent current cap is always cleared on daemon restart before
    # accepting new writes (when the attached Lightning service is accessible).
    control_panel.init(sys.modules[__name__],LOG)
    control_panel.boot_recover()
    if SOCK.is_symlink():SOCK.unlink()
    elif SOCK.exists():SOCK.unlink()
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    server.bind(str(SOCK));os.chown(SOCK,501,501);os.chmod(SOCK,0o600)
    server.listen(4)
    append('DAEMON READY: local socket available; only mobile/root peers allowed')
    control_panel.serve_panel()
    while True:
        conn,_=server.accept()
        with conn:
            try:
                try:
                    uid,gid=peer_identity(conn)
                except Exception as err:
                    append(f'IPC peer verification failed: {type(err).__name__}: {err}')
                    conn.sendall(b'ERR 60\n');continue
                if uid not in (501,0):
                    append(f'IPC rejected peer uid={uid}')
                    conn.sendall(b'ERR 61\n');continue
                command=conn.recv(32).decode('ascii','replace').strip('\0\r\n ')
                if command=='PROBE':
                    # The GUI's initial probe MUST NOT fail simply because no USB
                    # *charging input* is proven attached. The one-tap TEST will
                    # enumerate & record all ports, and will refuse any writes
                    # if no attached input-current path can be identified.
                    # This deliberately means socket/helper online, NOT hardware ready.
                    append('PROBE ONLINE: root IPC service is responding. USB input attachment not yet verified; press Test for read-only port diagnosis before any possible write.')
                    status=0
                elif command=='TEST':
                    status=run_test()
                elif command=='STATE':
                    import json
                    conn.sendall((json.dumps(control_panel.status_payload(),separators=(',',':'))+'\n').encode())
                    continue
                elif command=='LOG':
                    contents=LOG.read_bytes()[-24000:] if LOG.exists() else b'No diagnostic log yet.'
                    conn.sendall(contents)
                    continue
                elif command.startswith('ENABLE '):
                    try:
                        requested=int(command[7:])
                        result=control_panel.do_enable(requested)
                        if result['ok']:
                            append('NATIVE APP: enable '+str(requested)+'mA verified')
                            conn.sendall(b'OK 0\n')
                        else:
                            append('NATIVE APP: enable refused: '+result['message'])
                            conn.sendall(('ERR '+result['message']+'\n').encode()[:400])
                    except Exception as e:
                        append('NATIVE APP ERROR: '+repr(e))
                        conn.sendall(('ERR '+repr(e)+'\n').encode()[:400])
                    continue
                elif command=='RESTART':
                    # Only the native UI sends RESTART; package maintenance and
                    # legacy diagnostics still send plain RESTORE (no power pulse).
                    result=control_panel.do_restore('native-app-or-package-removal')
                    if not result['ok']:
                        conn.sendall(('ERR '+result['message']+'\n').encode()[:400]);continue
                    restart=control_panel.do_power_restart('native-app')
                    conn.sendall(('OK 0\n' if restart['ok'] else 'ERR '+restart['message']+'\n').encode()[:400])
                    continue
                elif command=='RESTORE_UPGRADE':
                    # Preserve the user-saved cap while dpkg temporarily stops
                    # the old daemon during an in-place package upgrade.
                    result=control_panel.do_restore('package-upgrade')
                    conn.sendall(('OK 0\n' if result['ok'] else 'ERR '+result['message']+'\n').encode()[:400])
                    continue
                elif command=='RESTORE':
                    # An earlier release could have cleared its state marker
                    # while real charging remained low until physical replug.
                    # Always offer the manual base-current refresh even with
                    # no saved state, but first restore any legacy timed test.
                    if not control_panel.read_state():
                        legacy=current_restoration('app-button',force=False)
                        if legacy!=0:
                            conn.sendall(f'ERR legacy restore failed {legacy}\n'.encode())
                            continue
                    result=control_panel.do_restore('native-app-or-package-removal')
                    conn.sendall(('OK 0\n' if result['ok'] else 'ERR '+result['message']+'\n').encode()[:400])
                    continue
                else:
                    status=62
                conn.sendall(('OK 0\n' if status==0 else f'ERR {status}\n').encode())
            except Exception as e:
                try:append(f'DAEMON IPC ERROR {type(e).__name__}: {e}')
                except Exception:pass
                try:conn.sendall(b'ERR 63\n')
                except Exception:pass


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--usb-power-watchdog':
        control_panel.init(sys.modules[__name__],LOG)
        sys.exit(control_panel.usb_power_watchdog(sys.argv[2]))
    if len(sys.argv)==4 and sys.argv[1]=='--panel-watchdog':
        control_panel.init(sys.modules[__name__],LOG)
        sys.exit(control_panel.watchdog(sys.argv[2],sys.argv[3]))
    if len(sys.argv)==3 and sys.argv[1]=='--watchdog':
        sys.exit(watchdog(sys.argv[2]))
    if len(sys.argv)>1:sys.exit(2)
    try:serve()
    except Exception as e:
        try:append(f'FATAL root daemon: {type(e).__name__}: {e}')
        except Exception:pass
        raise
