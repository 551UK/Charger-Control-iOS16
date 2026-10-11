#import <UIKit/UIKit.h>
#import <Foundation/Foundation.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

static NSString *const kSocketPath=@"/var/jb/var/mobile/551UK-ChargeRateTest-v052/chargerated.sock";
static NSString *request(NSString *command) {
    int fd=socket(AF_UNIX,SOCK_STREAM,0);
    if(fd<0)return [NSString stringWithFormat:@"ERR socket %d",errno];
    struct sockaddr_un sa;memset(&sa,0,sizeof(sa));sa.sun_family=AF_UNIX;
    strlcpy(sa.sun_path,[kSocketPath UTF8String],sizeof(sa.sun_path));
    struct timeval tv={4,0};
    setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&tv,sizeof(tv));
    setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&tv,sizeof(tv));
    if(connect(fd,(struct sockaddr *)&sa,sizeof(sa))!=0) {
        int e=errno;close(fd);return [NSString stringWithFormat:@"ERR helper offline (%d)",e];
    }
    NSData *cmd=[[command stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding];
    if(write(fd,cmd.bytes,cmd.length)!=(ssize_t)cmd.length){close(fd);return @"ERR command send failed";}
    shutdown(fd,SHUT_WR);
    NSMutableData *out=[NSMutableData data];char buf[2048];ssize_t n;
    while((n=read(fd,buf,sizeof(buf)))>0&&out.length<64000)[out appendBytes:buf length:n];
    close(fd);
    NSString *response=[[NSString alloc] initWithData:out encoding:NSUTF8StringEncoding];
    return response?:@"ERR invalid helper response";
}
static NSString *reading(NSDictionary *d,NSString *key,NSString *suffix) {
    id v=d[key];
    if(!v||v==[NSNull null]||![v respondsToSelector:@selector(doubleValue)])return @"—";
    return [NSString stringWithFormat:@"%.2f%@",[v doubleValue],suffix?:@""];
}
static NSString *watts(NSDictionary*d,NSString*k,NSInteger divide) {
    id v=d[k];
    if(![v isKindOfClass:NSNumber.class])return @"—";
    return [NSString stringWithFormat:@"%.2f W",[v doubleValue]/divide];
}
static UIColor *rgb(CGFloat r,CGFloat g,CGFloat b){return [UIColor colorWithRed:r green:g blue:b alpha:1];}
@interface ChargeViewController:UIViewController
@property(nonatomic,strong)UIScrollView *scroll;
@property(nonatomic,strong)UILabel *statusLabel,*chargerLabel,*inputLabel,*batteryLabel,*effectiveLabel,*capTitleLabel,*capLabel,*minCapLabel,*maxCapLabel,*chargingVoltageLabel;
@property(nonatomic,strong)UISlider *currentSlider;
@property(nonatomic,strong)UISwitch *enableSwitch;
@property(nonatomic,strong)UIButton *applyButton,*restoreButton,*githubButton;
@property(nonatomic,strong)NSTimer *timer;
@property(nonatomic,assign)BOOL busy;
@end
@implementation ChargeViewController
- (UILabel*)makeLabel:(NSString*)text font:(CGFloat)sz y:(CGFloat)y color:(UIColor*)col {
    UILabel *lab=[[UILabel alloc]initWithFrame:CGRectMake(18,y,330,44)];
    lab.text=text;lab.numberOfLines=0;lab.textColor=col;lab.font=[UIFont systemFontOfSize:sz weight:UIFontWeightMedium];
    [self.scroll addSubview:lab];return lab;
}
- (UIButton*)makeButton:(NSString*)title y:(CGFloat)y color:(UIColor*)color action:(SEL)sel{
    UIButton *button=[UIButton buttonWithType:UIButtonTypeSystem];
    button.frame=CGRectMake(18,y,330,48);
    button.backgroundColor=color;button.layer.cornerRadius=12;
    [button setTitle:title forState:UIControlStateNormal];
    [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    button.titleLabel.font=[UIFont systemFontOfSize:16 weight:UIFontWeightSemibold];
    [button addTarget:self action:sel forControlEvents:UIControlEventTouchUpInside];
    [self.scroll addSubview:button];return button;
}
- (void)viewDidLoad{
    [super viewDidLoad];self.view.backgroundColor=rgb(.05,.075,.12);
    self.scroll=[[UIScrollView alloc]initWithFrame:self.view.bounds];
    self.scroll.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;
    [self.view addSubview:self.scroll];
    UIColor *white=rgb(.95,.97,1),*mute=rgb(.6,.68,.79),*cyan=rgb(.40,.82,1);
    // Centered app heading, without the obsolete 551UK/Dopamine/iOS subtitle.
    UILabel *heading=[self makeLabel:@"USB Charge Control" font:27 y:32 color:white];
    heading.textAlignment=NSTextAlignmentCenter;
    heading.numberOfLines=1;
    // Equal 14pt gaps above the two blue section headings.
    self.statusLabel=[self makeLabel:@"Connecting to charging controller…" font:13 y:85 color:cyan];
    self.statusLabel.frame=CGRectMake(18,85,330,36);
    [self makeLabel:@"CHARGING DATA" font:13 y:135 color:cyan].frame=CGRectMake(18,135,330,24);
    // Uniform 16pt, medium-weight and white readouts. The input-rail mA
    // number alone remains green so the key value stands out.
    self.chargerLabel=[self makeLabel:@"Charger Rating: —" font:16 y:163 color:white];
    self.chargerLabel.frame=CGRectMake(18,163,330,30);
    self.inputLabel=[self makeLabel:@"Input Rail: — W  |  — mA" font:16 y:195 color:white];
    self.inputLabel.frame=CGRectMake(18,195,330,30);
    [self setInputRailWatts:@"— W" current:@"— mA"];
    self.batteryLabel=[self makeLabel:@"Battery: — W  |  — mA" font:16 y:227 color:white];
    self.batteryLabel.frame=CGRectMake(18,227,330,30);
    self.effectiveLabel=[self makeLabel:@"Current USB limit: —" font:16 y:259 color:white];
    self.effectiveLabel.frame=CGRectMake(18,259,330,30);
    self.chargingVoltageLabel=[self makeLabel:@"Charging: — | USB Voltage: —" font:16 y:291 color:white];
    self.chargingVoltageLabel.frame=CGRectMake(18,291,330,30);
    // Last data row ends at 321; 14pt gap before the blue cap heading.
    self.capTitleLabel=[self makeLabel:@"CHARGING CURRENT CAP" font:13 y:335 color:cyan];
    self.capTitleLabel.numberOfLines=1;
    self.capLabel=[self makeLabel:@"Selected: 1000 mA" font:14 y:335 color:white];
    self.capLabel.numberOfLines=1;
    self.capLabel.textAlignment=NSTextAlignmentRight;
    self.currentSlider=[[UISlider alloc]initWithFrame:CGRectMake(18,374,330,34)];
    self.currentSlider.minimumValue=500;self.currentSlider.maximumValue=2400;self.currentSlider.value=1000;
    [self.currentSlider addTarget:self action:@selector(sliderChanged:) forControlEvents:UIControlEventValueChanged];
    [self.currentSlider addTarget:self action:@selector(sliderDone:) forControlEvents:UIControlEventTouchUpInside|UIControlEventTouchUpOutside];
    [self.scroll addSubview:self.currentSlider];
    self.minCapLabel=[self makeLabel:@"500mA" font:12 y:404 color:mute];
    self.maxCapLabel=[self makeLabel:@"2400mA" font:12 y:404 color:mute];
    self.minCapLabel.numberOfLines=1;
    self.maxCapLabel.numberOfLines=1;
    self.maxCapLabel.textAlignment=NSTextAlignmentRight;
    [self makeLabel:@"Enable current limit" font:17 y:438 color:white].frame=CGRectMake(18,438,220,38);
    self.enableSwitch=[[UISwitch alloc]initWithFrame:CGRectMake(274,439,55,36)];
    [self.enableSwitch addTarget:self action:@selector(toggleChanged:) forControlEvents:UIControlEventValueChanged];
    [self.scroll addSubview:self.enableSwitch];
    self.applyButton=[self makeButton:@"Apply selected current" y:494 color:rgb(.08,.45,.77) action:@selector(applyTapped:)];
    self.restoreButton=[self makeButton:@"Restore normal charging" y:554 color:rgb(.39,.20,.23) action:@selector(restoreTapped:)];
    // Keep the short iOS telemetry delay disclaimer, but remove the other two explanatory paragraphs.
    [self makeLabel:@"Live power readings may take 15–20 seconds to update while waiting for iOS telemetry. USB cap confirmation is separate from these readings." font:12 y:613 color:mute].frame=CGRectMake(18,613,330,66);
    self.scroll.contentSize=CGSizeMake(365,694);
    // Keep the repository link visible at the bottom, even when the data scrolls.
    self.githubButton=[UIButton buttonWithType:UIButtonTypeSystem];
    self.githubButton.backgroundColor=rgb(.05,.075,.12);
    [self.githubButton setTitle:@"GitHub Repository ↗" forState:UIControlStateNormal];
    [self.githubButton setTitleColor:cyan forState:UIControlStateNormal];
    self.githubButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    [self.githubButton addTarget:self action:@selector(openRepository:) forControlEvents:UIControlEventTouchUpInside];
    [self.view addSubview:self.githubButton];
    self.scroll.contentInset=UIEdgeInsetsMake(0,0,65,0);
    self.scroll.scrollIndicatorInsets=UIEdgeInsetsMake(0,0,65,0);
    NSInteger saved=[[NSUserDefaults standardUserDefaults]integerForKey:@"selectedCurrent"];
    if(saved>=500&&saved<=2400)self.currentSlider.value=saved;
    [self sliderChanged:self.currentSlider];[self refresh:nil];
    self.timer=[NSTimer scheduledTimerWithTimeInterval:2.0 target:self selector:@selector(refresh:) userInfo:nil repeats:YES];
}
- (void)viewDidLayoutSubviews{
    [super viewDidLayoutSubviews];
    CGFloat w=self.view.bounds.size.width, usable=MAX(0,w-36);
    for(UIView *v in self.scroll.subviews){
        if(v==self.enableSwitch){v.frame=CGRectMake(w-84,v.frame.origin.y,55,36);continue;}
        CGRect f=v.frame;f.size.width=usable;v.frame=f;
    }
    // Fit the cyan heading and selected current side-by-side on one row.
    CGFloat selectedWidth=MIN(144,usable*.43);
    self.capTitleLabel.frame=CGRectMake(18,335,usable-selectedWidth-4,32);
    self.capLabel.frame=CGRectMake(18+usable-selectedWidth,335,selectedWidth,32);
    // Align endpoint captions with the slider track, not the middle of the screen.
    self.minCapLabel.frame=CGRectMake(18,404,94,24);
    self.maxCapLabel.frame=CGRectMake(w-18-94,404,94,24);
    self.githubButton.frame=CGRectMake(18,CGRectGetMaxY(self.view.safeAreaLayoutGuide.layoutFrame)-46,usable,42);
    self.scroll.contentSize=CGSizeMake(w,694);
}
- (void)openRepository:(id)sender{
    (void)sender;
    NSURL *url=[NSURL URLWithString:@"https://github.com/551UK/Charger-Control-iOS16"];
    [[UIApplication sharedApplication] openURL:url options:@{} completionHandler:nil];
}
- (void)setInputRailWatts:(NSString *)power current:(NSString *)current{
    // Keep the rail label and watts white, but make the live mA value
    // green at all times, including the initial/unavailable placeholder.
    NSString *prefix=[NSString stringWithFormat:@"Input Rail: %@  |  ",power];
    NSMutableAttributedString *line=[[NSMutableAttributedString alloc]
        initWithString:[prefix stringByAppendingString:current]
        attributes:@{
            NSForegroundColorAttributeName: rgb(.95,.97,1),
            NSFontAttributeName: self.inputLabel.font
        }];
    [line addAttribute:NSForegroundColorAttributeName
        value:rgb(.38,.87,.65)
        range:NSMakeRange(prefix.length,current.length)];
    self.inputLabel.attributedText=line;
}
- (NSInteger)selectedMA{return (NSInteger)(roundf(self.currentSlider.value/100.0f)*100);}
- (void)sliderChanged:(id)sender{
    NSInteger ma=[self selectedMA];
    self.capLabel.text=[NSString stringWithFormat:@"Selected: %ld mA",(long)ma];
    (void)sender;
}
- (void)sliderDone:(id)sender{
    NSInteger ma=[self selectedMA];self.currentSlider.value=ma;
    [[NSUserDefaults standardUserDefaults]setInteger:ma forKey:@"selectedCurrent"];
    if(self.enableSwitch.isOn)[self applyTapped:sender];
}
- (void)presentStatus:(NSString*)message ok:(BOOL)ok{
    self.statusLabel.text=message;
    self.statusLabel.textColor=ok?rgb(.38,.87,.65):rgb(.98,.55,.49);
}
- (void)refresh:(id)sender{
    (void)sender;
    if(self.busy)return;
    NSString *raw=request(@"STATE");
    NSData *data=[raw dataUsingEncoding:NSUTF8StringEncoding];
    NSDictionary *d=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil;
    if(![d isKindOfClass:NSDictionary.class]){[self presentStatus:@"Charging controller offline." ok:NO];return;}
    self.chargerLabel.text=[NSString stringWithFormat:@"Charger Rating: %@",watts(d,@"adapter_w",1)];
    NSNumber *railMA=[d[@"system_ma"] isKindOfClass:NSNumber.class]?d[@"system_ma"]:nil;
    NSString *railMAtext=railMA?[NSString stringWithFormat:@"%.0f mA",railMA.doubleValue]:@"— mA";
    [self setInputRailWatts:watts(d,@"system_mw",1000) current:railMAtext];
    NSNumber *mv=[d[@"battery_mv"] isKindOfClass:NSNumber.class]?d[@"battery_mv"]:nil;
    NSNumber *ma=[d[@"battery_ma"] isKindOfClass:NSNumber.class]?d[@"battery_ma"]:nil;
    NSString *batteryW=mv&&ma?[NSString stringWithFormat:@"%.2f W",mv.doubleValue*ma.doubleValue/1000000.0]:@"— W";
    NSString *batteryMA=ma?[NSString stringWithFormat:@"%.0f mA",ma.doubleValue]:@"— mA";
    self.batteryLabel.text=[NSString stringWithFormat:@"Battery: %@  |  %@",batteryW,batteryMA];
    NSString *chargingText=[d[@"charging"] respondsToSelector:@selector(intValue)]&&[d[@"charging"] intValue]==1?@"Yes":@"No";
    NSString *voltageText=[d[@"usb_mv"] isKindOfClass:NSNumber.class]?[NSString stringWithFormat:@"%.2f V",[d[@"usb_mv"] doubleValue]/1000.0]:@"—";
    self.chargingVoltageLabel.text=[NSString stringWithFormat:@"Charging: %@ | USB Voltage: %@",chargingText,voltageText];
    self.effectiveLabel.text=[NSString stringWithFormat:@"Effective USB current cap: %@ mA",reading(d,@"usb_ma",@"")];
    BOOL enabled=[d[@"enabled"] respondsToSelector:@selector(boolValue)]&&[d[@"enabled"] boolValue];
    [self.enableSwitch setOn:enabled animated:NO];
    NSString *msg=[d[@"message"] isKindOfClass:NSString.class]?d[@"message"]:@"";
    // Informational controller messages are not failures.
    NSString *status=msg.length?msg:(enabled?@"USB current cap ACTIVE":@"Normal charging / no cap active");
    NSString *lower=status.lowercaseString;
    BOOL positive=[lower hasPrefix:@"charger connected"]
        || [lower containsString:@"cap applied"]
        || [lower containsString:@"usb cap active"]
        || [lower containsString:@"normal charging"]
        || [lower containsString:@"no cap active"];
    [self presentStatus:status ok:positive];
}
- (void)sendAction:(NSString*)cmd success:(NSString*)name{
    if(self.busy)return;self.busy=YES;[self presentStatus:[NSString stringWithFormat:@"%@…",name] ok:YES];
    NSString *raw=request(cmd);
    BOOL ok=[raw hasPrefix:@"OK "];NSString *msg=[raw stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    self.busy=NO;[self refresh:nil];
    NSString *successMsg=[cmd isEqualToString:@"RESTORE"]
        ? @"USB cap released. Checking charging recovery…"
        : [NSString stringWithFormat:@"%ldmA cap applied — live readings may be delayed",(long)[self selectedMA]];
    [self presentStatus:ok?successMsg:[NSString stringWithFormat:@"Failed: %@",msg] ok:ok];
    if(!ok)self.enableSwitch.on=[cmd hasPrefix:@"ENABLE"]?NO:self.enableSwitch.on;
}
- (void)toggleChanged:(UISwitch*)sender{
    if(sender.isOn)[self sendAction:[NSString stringWithFormat:@"ENABLE %ld",(long)[self selectedMA]] success:@"Current cap"];
    else [self sendAction:@"RESTORE" success:@"Normal charging"];
}
- (void)applyTapped:(id)sender{
    (void)sender;
    [self sendAction:[NSString stringWithFormat:@"ENABLE %ld",(long)[self selectedMA]] success:@"Current cap"];
}
- (void)restoreTapped:(id)sender{(void)sender;[self sendAction:@"RESTORE" success:@"Normal charging"];}
- (void)dealloc{[self.timer invalidate];}
@end
@interface ChargeAppDelegate:UIResponder <UIApplicationDelegate>
@property(nonatomic,strong)UIWindow *window;
@end
@implementation ChargeAppDelegate
- (BOOL)application:(UIApplication*)app didFinishLaunchingWithOptions:(NSDictionary*)opts{
    (void)app;(void)opts;
    self.window=[[UIWindow alloc]initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController=[ChargeViewController new];
    [self.window makeKeyAndVisible];return YES;
}
@end
int main(int argc,char **argv){@autoreleasepool{return UIApplicationMain(argc,argv,nil,NSStringFromClass(ChargeAppDelegate.class));}}
