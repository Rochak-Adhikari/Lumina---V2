# Fixed native provider. Never interpolate request data into executable code.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$r = [Console]::In.ReadToEnd() | ConvertFrom-Json
$mutating = $false
try {
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, WindowsBase
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class LuminaNative {
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h,int n);
 [DllImport("user32.dll")] public static extern IntPtr MonitorFromWindow(IntPtr h,uint f);
 [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr c);
 [DllImport("user32.dll")] public static extern bool SystemParametersInfo(uint a,uint b,ref int c,uint d);
 [DllImport("user32.dll",EntryPoint="SystemParametersInfoW")] public static extern bool SetMouse(uint a,uint b,IntPtr c,uint d);
 [StructLayout(LayoutKind.Sequential)] public struct LASTINPUTINFO { public uint size; public uint tick; }
 [DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LASTINPUTINFO i);
 public static uint InputTick() {var i=new LASTINPUTINFO(); i.size=8; if(!GetLastInputInfo(ref i)) throw new Exception(); return i.tick;}
}
"@
[void][LuminaNative]::SetProcessDpiAwarenessContext([IntPtr](-4))
function Fail($code) { throw [InvalidOperationException]::new($code) }
function Json($value) { ConvertTo-Json -InputObject $value -Depth 25 -Compress }
function Canonical($value) {
 if($null -eq $value){return $null}
 if($value -is [Collections.IDictionary]) { $o=[ordered]@{}; foreach($k in @($value.Keys | Sort-Object)){$o[$k]=Canonical $value[$k]}; return $o }
 if($value -is [pscustomobject]) { $o=[ordered]@{}; foreach($k in @($value.PSObject.Properties.Name | Sort-Object)){$o[$k]=Canonical $value.$k}; return $o }
 if($value -is [array]) { $o=@(); foreach($v in $value){$o+=,(Canonical $v)}; return ,$o }
 return $value
}
function Hash($value) {
 $h = [Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($r.secret))
 try { $bytes=[Text.Encoding]::UTF8.GetBytes((Json (Canonical $value))); return [Convert]::ToBase64String($h.ComputeHash($bytes)) } finally { $h.Dispose() }
}
function Identity($e) {
 $c=$e.Current; $p=Get-Process -Id $c.ProcessId
 return "$($c.NativeWindowHandle):$($c.ProcessId):$($p.StartTime.ToUniversalTime().Ticks):$([string]::Join('.', $e.GetRuntimeId()))"
}
function Windows {
 $all=[Windows.Automation.AutomationElement]::RootElement.FindAll([Windows.Automation.TreeScope]::Children,[Windows.Automation.Condition]::TrueCondition)
 $rows=@(); foreach($e in $all) { try { if($e.Current.NativeWindowHandle -ne 0) { $rows+=@{id=(Identity $e); name=$e.Current.Name; hwnd=$e.Current.NativeWindowHandle} } } catch {} }
 return $rows
}
function Window($id) {
 $parts=$id.Split(':'); if($parts.Length -ne 4) { Fail 'invalid_window' }
 $h=[IntPtr]([long]$parts[0]); if(-not [LuminaNative]::IsWindow($h)) { Fail 'missing_window' }
 $e=[Windows.Automation.AutomationElement]::FromHandle($h)
 if((Identity $e) -cne $id) { Fail 'stale_window' }; return $e
}
function Control($e) {
 $c=$e.Current; $patterns=@($e.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName.Replace('PatternIdentifiers.Pattern','').Replace('Pattern','') })
 $private=$c.IsPassword -or $c.ControlType -eq [Windows.Automation.ControlType]::Edit -or $patterns -contains 'Value'
 $b=$c.BoundingRectangle
 $state=@{id=([string]::Join('.', $e.GetRuntimeId())); name=$(if($private){'[redacted]'}else{$c.Name}); automation_id=$c.AutomationId; role=$c.ControlType.ProgrammaticName; enabled=$c.IsEnabled; password=$c.IsPassword; offscreen=$c.IsOffscreen; patterns=$patterns; bounds=@($b.X,$b.Y,$b.Width,$b.Height)}
 if($patterns -contains 'Value' -and -not $c.IsPassword) {
  $v=$e.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern).Current
  $state.value_binding=Hash $v.Value; $state.readonly=$v.IsReadOnly
 }
 if($patterns -contains 'Toggle') { $state.toggle=[int]$e.GetCurrentPattern([Windows.Automation.TogglePattern]::Pattern).Current.ToggleState }
 return $state
}
function Snapshot($e) {
 $script:elements=@{}
 $tick=[LuminaNative]::InputTick(); $h=[IntPtr]$e.Current.NativeWindowHandle
 $controls=@(); $nodes=[Collections.Generic.Queue[object]]::new(); $nodes.Enqueue($e)
 $walker=[Windows.Automation.TreeWalker]::ControlViewWalker
 while($nodes.Count -gt 0 -and $controls.Count -lt 256) {
  $node=$nodes.Dequeue(); $row=Control $node; $controls+=,$row; $script:elements[$row.id]=$node
  $child=$walker.GetFirstChild($node)
  while($null -ne $child -and $nodes.Count -lt 256) { $nodes.Enqueue($child); $child=$walker.GetNextSibling($child) }
 }
 return @{ok=$true; window=(Identity $e); controls=$controls; truncated=($nodes.Count -gt 0); foreground=[LuminaNative]::GetForegroundWindow().ToInt64(); input_tick=$tick; monitor=[LuminaNative]::MonitorFromWindow($h,2).ToInt64(); dpi=[LuminaNative]::GetDpiForWindow($h); captured_at=[DateTime]::UtcNow.ToString('o'); bounds=(Control $e).bounds}
}
function Setting($kind,$target) {
 switch($kind) {
  'audio' { return [LuminaAudio]::Read($target) }
  'brightness' {
   try { $items=@(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness | Where-Object { $_.InstanceName -ceq $target -and $_.Active }) } catch { Fail 'missing_or_unsupported_monitor' }
   if($items.Count -ne 1) { Fail 'missing_or_unsupported_monitor' }
   return @{identity=$target; value=[int]$items[0].CurrentBrightness}
  }
  'mouse_speed' { if($target -cne 'system'){Fail 'invalid_target'}; $v=0; if(-not [LuminaNative]::SystemParametersInfo(0x70,0,[ref]$v,0)){Fail 'unsupported_setting'}; return @{identity='system';value=$v} }
  'window' { $e=Window $target; $h=[IntPtr]$e.Current.NativeWindowHandle; $v='normal'; if([LuminaNative]::IsIconic($h)){$v='minimized'}elseif([LuminaNative]::IsZoomed($h)){$v='maximized'}; return @{identity=(Identity $e);value=$v} }
  default { Fail 'unsupported_setting' }
 }
}
if($r.kind -eq 'audio') { . (Join-Path $PSScriptRoot 'computer_audio_helper.ps1') }
switch($r.operation) {
 'windows' { $out=@{ok=$true;windows=@(Windows)} }
 'inspect' { $out=Snapshot (Window $r.window) }
 'settings_list' {
  switch($r.kind) {
   'brightness' { try { $targets=@(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness | Where-Object Active | ForEach-Object { @{id=$_.InstanceName;value=[int]$_.CurrentBrightness} }) } catch { Fail 'missing_or_unsupported_monitor' }; $out=@{ok=$true;targets=$targets} }
   'window' {$out=@{ok=$true;targets=@(Windows)}}
   'mouse_speed' {$out=@{ok=$true;targets=@(@{id='system'})}}
   'audio' {$out=@{ok=$true;targets=@([LuminaAudio]::List())}}
   default {Fail 'unsupported_setting'}
  }
 }
 'settings_get' { $out=@{ok=$true;state=(Setting $r.kind $r.target)} }
 'settings_apply' {
  $before=Setting $r.kind $r.target
  if((Hash $before) -cne (Hash $r.expected)){Fail 'stale_setting'}
  switch($r.kind) {
   'audio' { $mutating=$true; [void][LuminaAudio]::Write($r.target,[float]$r.value.volume,[bool]$r.value.mute) }
   'brightness' {
    if($r.value -isnot [int] -or $r.value -lt 0 -or $r.value -gt 100){Fail 'invalid_value'}
    $m=@(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods | Where-Object { $_.InstanceName -ceq $r.target })
    if($m.Count -ne 1){Fail 'missing_or_unsupported_monitor'}
    if((Hash (Setting $r.kind $r.target)) -cne (Hash $r.expected)){Fail 'stale_setting'}
    $mutating=$true; $result=Invoke-CimMethod -InputObject $m[0] -MethodName WmiSetBrightness -Arguments @{Timeout=[uint32]0;Brightness=[byte]$r.value}
    if($result.ReturnValue -ne 0){Fail 'setting_failed'}
   }
   'mouse_speed' { if($r.value -isnot [int] -or $r.value -lt 1 -or $r.value -gt 20){Fail 'invalid_value'}; $mutating=$true; if(-not [LuminaNative]::SetMouse(0x71,0,[IntPtr]([int]$r.value),0)){Fail 'setting_failed'} }
   'window' { $e=Window $r.target; $codes=@{normal=9;minimized=6;maximized=3}; if(-not $codes.ContainsKey([string]$r.value)){Fail 'invalid_value'}; $mutating=$true; [void][LuminaNative]::ShowWindowAsync([IntPtr]$e.Current.NativeWindowHandle,$codes[[string]$r.value]) }
  }
  $after=Setting $r.kind $r.target
  $verified=(Hash $after.value) -ceq (Hash $r.value)
  if($r.kind -eq 'audio') { $verified=([Math]::Abs($after.value.volume-$r.value.volume) -lt 0.00001 -and $after.value.mute -eq $r.value.mute) }
  $out=@{ok=$true;status=$(if($verified){'verified'}else{'unverified'});verified=$verified;state=$after;previous=$before}
 }
 'control_apply' {
  $e=Window $r.window; $now=Snapshot $e
  if(-not $r.focus) {
   if($now.foreground -ne $e.Current.NativeWindowHandle -or $now.foreground -ne $r.expected.foreground){Fail 'stale_focus'}
   if($now.input_tick -ne $r.expected.input_tick){Fail 'user_takeover'}
  }
  if($now.dpi -ne $r.expected.dpi -or $now.monitor -ne $r.expected.monitor -or (Hash $now.bounds) -cne (Hash $r.expected.bounds)){Fail 'stale_geometry'}
  if((Hash $now.controls) -cne (Hash $r.expected.controls)){Fail 'stale_controls'}
  if($r.focus) {
   # Confirmation explicitly includes focus. Never attach input threads, inject
   # keys or bypass Windows foreground restrictions. A denial fails closed.
   if([LuminaNative]::InputTick() -ne $now.input_tick -or [LuminaNative]::GetForegroundWindow().ToInt64() -ne $now.foreground){Fail 'user_takeover'}
   $mutating=$true
   if(-not [LuminaNative]::SetForegroundWindow([IntPtr]$e.Current.NativeWindowHandle)){Fail 'focus_denied'}
   $fresh=Snapshot (Window $r.window)
   if($fresh.foreground -ne $e.Current.NativeWindowHandle){Fail 'stale_focus'}
   if($fresh.input_tick -ne $now.input_tick){Fail 'user_takeover'}
   if((Hash $fresh.controls) -cne (Hash $now.controls)){Fail 'stale_controls'}
   if($fresh.monitor -ne $now.monitor -or $fresh.dpi -ne $now.dpi -or (Hash $fresh.bounds) -cne (Hash $now.bounds)){Fail 'stale_geometry'}
   $now=$fresh
  }
  if(-not $script:elements.ContainsKey([string]$r.control.id)){Fail 'ambiguous_or_missing_control'}
  $target=$script:elements[[string]$r.control.id]; $c=Control $target
  if((Hash $c) -cne (Hash $r.control) -or -not $c.enabled -or $c.password -or $c.offscreen){Fail 'stale_control'}
  if([LuminaNative]::GetForegroundWindow().ToInt64() -ne $now.foreground -or [LuminaNative]::InputTick() -ne $now.input_tick){Fail 'user_takeover'}
  switch($r.verb) {
   'invoke' { $p=$target.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern); $mutating=$true; $p.Invoke() }
   'type' { $p=$target.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern); if($p.Current.IsReadOnly -or $r.text.Length -gt 8192){Fail 'unsupported_control'}; $mutating=$true; $p.SetValue([string]$r.text) }
   default {Fail 'unsupported_action'}
  }
  $after=Snapshot (Window $r.window)
  $changed=(Hash $after.controls) -cne (Hash $now.controls)
  $verified=$false
  if($r.verb -eq 'type') { $verified=(Hash $p.Current.Value) -ceq (Hash ([string]$r.text)) }
  if($r.verb -eq 'type' -and $r.text.Length -gt 0) {
   # Apps may mirror input into labels; never echo this request's text.
   foreach($row in $after.controls) { $row.name=$row.name.Replace([string]$r.text,'[redacted]'); $row.automation_id=$row.automation_id.Replace([string]$r.text,'[redacted]') }
  }
  $out=@{ok=$true;status=$(if($verified){'verified'}elseif($changed){'observed_change'}else{'unverified'});verified=$verified;observed_change=$changed;observation=$after}
 }
 default {Fail 'unsupported_action'}
}
[Console]::Out.Write((Json $out))
} catch {
 $code='provider_failed'
 $allowed=@('invalid_window','missing_window','stale_window','missing_or_unsupported_monitor','invalid_target','unsupported_setting','stale_setting','invalid_value','setting_failed','stale_focus','focus_denied','user_takeover','stale_geometry','stale_controls','ambiguous_or_missing_control','stale_control','unsupported_control','unsupported_action')
 if($_.Exception.Message -in $allowed){$code=$_.Exception.Message}
 $inner=$_.Exception
 while($null -ne $inner) {
  if($inner.Message -eq 'disconnected_endpoint'){$code='disconnected_endpoint'}
  if($inner.HResult -eq -2147023728){$code='missing_endpoint'}
  $inner=$inner.InnerException
 }
 [Console]::Out.Write((ConvertTo-Json -Compress @{ok=$false;status=$code;error=$code;outcome=$(if($mutating){'unknown'}else{'not_started'})}))
}

