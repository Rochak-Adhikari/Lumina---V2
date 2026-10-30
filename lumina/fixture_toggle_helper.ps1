# One private, parent-supervised fixture Toggle. Not a general UIA executor.
# stdin is inherited from the Runtime; no argv accepts targets or code.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$raw=[Console]::ReadLine()
if(!$raw -or $raw.Length -gt 4096){exit 2}
$phase='schema'
try {
 $r=$raw|ConvertFrom-Json
 $keys='action_id,before,birth,control_id,deadline,decoy,label,nonce,operation,pid,scope,target,version,window'
 if((@($r.PSObject.Properties.Name|Sort-Object)-join ',') -cne $keys){throw 'invalid_schema'}
 foreach($key in @('operation','nonce','scope','before','control_id','action_id','birth')){
  if($r.$key -isnot [string]){throw 'invalid_string'}
 }
 if($r.version -isnot [int]){throw 'invalid_version'}
 if($r.version -ne 1 -or $r.operation -cne 'toggle_external_fixture' -or
    $r.nonce -cnotmatch '^[0-9a-f]{32}$' -or $r.scope -cnotmatch '^[0-9a-f]{64}$' -or
    $r.before -cnotmatch '^[01]:0:(0|[1-9][0-9]{0,5})$' -or
    $r.control_id -cnotmatch '^-?[0-9]+(\.-?[0-9]+){1,15}$' -or
    $r.action_id -cnotmatch '^[a-zA-Z0-9_-]{16,128}$' -or $r.birth -cnotmatch '^[1-9][0-9]{1,19}$'){throw 'invalid_scope'}
 foreach($key in @('pid','window','target','decoy','label','deadline')){
  if($r.$key -isnot [long] -and $r.$key -isnot [int]){throw 'invalid_integer'}
  if($r.$key -le 0){throw 'invalid_integer'}
 }
 if(@($r.window,$r.target,$r.decoy,$r.label|Select-Object -Unique).Count -ne 4){throw 'duplicate_target'}
 if($r.deadline -le [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() -or
    $r.deadline -gt [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()+5000){throw 'invalid_deadline'}
 $hash=[Security.Cryptography.SHA256]::Create()
 try {$request=([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::ASCII.GetBytes($raw)))).Replace('-','').ToLowerInvariant()}
 finally {$hash.Dispose()}
 $phase='assembly'
 Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,UIAutomationClientsideProviders,WindowsBase
 $phase='compile'
 Add-Type -ReferencedAssemblies @([Windows.Automation.ClientSettings].Assembly.Location,
  [Windows.Automation.AutomationPattern].Assembly.Location,
  [UIAutomationClientsideProviders.UIAutomationClientSideProviders].Assembly.Location,
  [Windows.Rect].Assembly.Location) -TypeDefinition @'
using System;
using System.Text;
using System.Threading;
using System.Runtime.InteropServices;
using System.Windows.Automation;
public sealed class FixtureToggle {
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("user32.dll")] static extern IntPtr GetParent(IntPtr h);
 [DllImport("user32.dll")] static extern int GetDlgCtrlID(IntPtr h);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h,StringBuilder s,int n);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr GetProp(IntPtr h,string name);
 [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr h,int index);
 [DllImport("user32.dll")] static extern bool IsWindowEnabled(IntPtr h);
 [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h,StringBuilder s,int n);
 [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access,bool inherit,int pid);
 [DllImport("kernel32.dll")] static extern bool GetProcessTimes(IntPtr h,out long creation,out long exit,out long kernel,out long user);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 readonly int pid,thread;readonly long birth,deadline;readonly IntPtr window,target,decoy,label;
 readonly string nonce,id,before,challenge,request;bool consumed;
 public int ThreadId {get{return thread;}}
 [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
 public FixtureToggle(int p,long w,long t,long d,long l,string n,long b,string i,string initial,long expires,string token,string digest) {
  if(Thread.CurrentThread.GetApartmentState()!=ApartmentState.MTA)throw new Exception("wrong_apartment");
  thread=Thread.CurrentThread.ManagedThreadId;pid=p;window=new IntPtr(w);target=new IntPtr(t);decoy=new IntPtr(d);label=new IntPtr(l);
  nonce=n;birth=b;id=i;before=initial;deadline=expires;challenge=token;request=digest;
  ClientSettings.RegisterClientSideProviderAssembly(typeof(UIAutomationClientsideProviders.UIAutomationClientSideProviders).Assembly.GetName());
  Validate();
 }
 static long Now(){return DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();}
 void Identity(IntPtr h,string klass,int number) {
  uint owner;GetWindowThreadProcessId(h,out owner);var name=new StringBuilder(128);GetClassName(h,name,128);
  if(owner!=pid||name.ToString()!=klass||!IsWindowEnabled(h)||!IsWindowVisible(h))throw new Exception("identity_changed");
  if(number!=0&&(GetParent(h)!=window||GetDlgCtrlID(h)!=number||
     GetProp(h,"LuminaM4RegisteredControl").ToInt64()!=Convert.ToInt64(nonce.Substring(0,8),16)+number))throw new Exception("control_changed");
 }
 TogglePattern Validate() {
  if(Thread.CurrentThread.ManagedThreadId!=thread||Thread.CurrentThread.GetApartmentState()!=ApartmentState.MTA||Now()>deadline)
   throw new Exception("expired_or_wrong_thread");
  var process=OpenProcess(0x1000,false,pid);if(process==IntPtr.Zero)throw new Exception("missing_process");
  try {long created,exit,kernel,user;if(!GetProcessTimes(process,out created,out exit,out kernel,out user)||created!=birth)throw new Exception("process_changed");}
  finally{CloseHandle(process);}
  Identity(window,"LuminaExternalFixture-"+nonce,0);Identity(target,"Button",4500);Identity(decoy,"Button",4501);Identity(label,"Static",4502);
  if((GetWindowLong(target,-16)&15)!=3||(GetWindowLong(decoy,-16)&15)!=3)throw new Exception("not_auto_checkbox");
  var text=new StringBuilder(128);GetWindowText(label,text,128);if(text.ToString()!=before)throw new Exception("revision_changed");
  var element=AutomationElement.FromHandle(target);var current=element.Current;
  if(current.ProcessId!=pid||current.NativeWindowHandle!=target.ToInt64()||current.ControlType!=ControlType.CheckBox||
    !current.IsEnabled||current.IsPassword||current.IsOffscreen||String.Join(".",element.GetRuntimeId())!=id)throw new Exception("uia_identity_changed");
  object pattern;if(!element.TryGetCurrentPattern(TogglePattern.Pattern,out pattern))throw new Exception("unsupported_toggle");
  var toggle=(TogglePattern)pattern;
  var other=(TogglePattern)AutomationElement.FromHandle(decoy).GetCurrentPattern(TogglePattern.Pattern);
  if((int)toggle.Current.ToggleState!=int.Parse(before.Substring(0,1))||other.Current.ToggleState!=ToggleState.Off)throw new Exception("state_changed");
  return toggle;
 }
 public void Commit(string token,string digest,long expires) {
  if(consumed||token!=challenge||digest!=request||expires<Now()||expires>Now()+750)throw new Exception("grant_rejected");
  consumed=true;
  var pattern=Validate();
  if(Now()>expires||Now()>deadline)throw new Exception("grant_expired");
  // Native validation failed. The standard Win32 proxy may synthesize keys
  // while acquiring focus. Do not revive this call from configuration or IPC.
  throw new InvalidOperationException("native_toggle_not_validated");
 }
}
'@
 $challenge=[Guid]::NewGuid().ToString('N')
 $phase='prepare'
 $client=[FixtureToggle]::new($r.pid,$r.window,$r.target,$r.decoy,$r.label,$r.nonce,[long]::Parse($r.birth),$r.control_id,$r.before,$r.deadline,$challenge,$request)
 [Console]::WriteLine((@{stage='ready';request=$request;challenge=$challenge;thread=$client.ThreadId;apartment='MTA'}|ConvertTo-Json -Compress))
 $line=[Console]::ReadLine()
 $phase='grant'
 if(!$line -or $line.Length -gt 1024){throw 'missing_grant'}
 $grant=$line|ConvertFrom-Json
 if((@($grant.PSObject.Properties.Name|Sort-Object)-join ',') -cne 'commit,expires,request' -or
    $grant.expires -isnot [long] -or $grant.commit -isnot [string] -or $grant.request -isnot [string]){throw 'invalid_grant'}
 $client.Commit($grant.commit,$grant.request,$grant.expires)
 [Console]::WriteLine((@{stage='returned';request=$request;thread=$client.ThreadId}|ConvertTo-Json -Compress))
} catch {
 $failure=$_.Exception.GetBaseException()
 [Console]::WriteLine((@{stage='rejected_or_uncertain';request=$request;phase=$phase;
     failure_type=$failure.GetType().FullName;hresult=$failure.HResult}|ConvertTo-Json -Compress))
 exit 2
} finally {
 $client=$null;[GC]::Collect();[GC]::WaitForPendingFinalizers()
}
