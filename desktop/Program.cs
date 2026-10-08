using System.Diagnostics;
using System.Net.Http;
using System.Net.Sockets;
using System.Text.Json;
using System.Runtime.InteropServices;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace LuminaDesktop;
static class Program {
 [DllImport("shell32.dll")] static extern int SetCurrentProcessExplicitAppUserModelID(string id);
 [STAThread] static void Main(string[] args) {
  ApplicationConfiguration.Initialize(); SetCurrentProcessExplicitAppUserModelID("LUMINA.Desktop");
  using var mutex=new Mutex(true,@"Local\LUMINA.Desktop",out bool first);
  if(!first){DarkDialog.Show("LUMINA is already open.","LUMINA");return;}
  try { using var backend=new Backend();
   if(args.Length==2&&args[0]=="--verify-backend"){
    try{backend.Initialize().GetAwaiter().GetResult();File.WriteAllText(args[1],JsonSerializer.Serialize(new{ok=true,root=backend.Root,python=backend.Python,origin=backend.Origin,owned=backend.Owned!=null,pid=backend.Owned?.Id,webview=CoreWebView2Environment.GetAvailableBrowserVersionString()}));}
    catch(Exception e){File.WriteAllText(args[1],JsonSerializer.Serialize(new{ok=false,error=e.Message}));Environment.ExitCode=1;}return;
   }
   using var window=new MainWindow(backend,args.Length==2&&args[0]=="--verify-window"?args[1]:null); Application.Run(window); }
  catch(Exception e){DarkDialog.Show(e.Message,"LUMINA startup failed",MessageBoxButtons.OK,MessageBoxIcon.Error);}
 }
}
sealed class Backend:IDisposable {
 public string Root="",Python="",Origin=""; public Process? Owned; public string Diagnostics="";
 readonly HttpClient http=new(new HttpClientHandler{AllowAutoRedirect=false,UseProxy=false}){Timeout=TimeSpan.FromSeconds(2)};
 public void Load(){
  var meta=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"runtime.json"))).RootElement;
  Root=Path.GetFullPath(meta.GetProperty("root").GetString()!,AppContext.BaseDirectory);
  Python=Path.GetFullPath(meta.GetProperty("python").GetString()!,AppContext.BaseDirectory);
  foreach(var p in new[]{Python,Path.Combine(Root,"lumina","desktop_backend.py"),Path.Combine(Root,"web","index.html"),Path.Combine(Root,"web","app.js"),Path.Combine(Root,"web","vendor","3d-force-graph.min.js"),Path.Combine(Root,"lumina.toml")})
   if(!File.Exists(p))throw new Exception("Required runtime file is missing: "+p);
 }
 ProcessStartInfo StartInfo(params string[] args){var s=new ProcessStartInfo(Python){WorkingDirectory=Root,UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true};foreach(var a in args)s.ArgumentList.Add(a);return s;}
 public async Task Initialize(){
  Load(); using(var probe=Process.Start(StartInfo("-m","lumina.desktop_backend","--describe"))!){
   var output=probe.StandardOutput.ReadToEndAsync();var error=probe.StandardError.ReadToEndAsync();
   try{await probe.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(15));}catch{probe.Kill(true);throw new Exception("Python configuration validation timed out.");}
   if(probe.ExitCode!=0)throw new Exception("Configured Python cannot load LUMINA. Check dependencies and lumina.toml.\n"+await error);
   var c=JsonDocument.Parse(await output).RootElement;var host=c.GetProperty("host").GetString()!;var port=c.GetProperty("port").GetInt32();
   if(host is not ("127.0.0.1" or "localhost" or "::1"))throw new Exception("Server must use a loopback host.");
   Origin=new UriBuilder("http",host,port).Uri.GetLeftPart(UriPartial.Authority);
  }
  if(await Healthy())return;
  var uri=new Uri(Origin);
  if(System.Net.NetworkInformation.IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners().Any(p=>p.Port==uri.Port))
    throw new InvalidOperationException("Port "+uri.Port+" is occupied by a service that did not identify as LUMINA API 1. Nothing was attached or stopped.");
  Owned=new Process{StartInfo=StartInfo("-m","lumina.desktop_backend")};
  Owned.OutputDataReceived+=(_,e)=>Record(e.Data);Owned.ErrorDataReceived+=(_,e)=>Record(e.Data);
  Owned.Start();Owned.BeginOutputReadLine();Owned.BeginErrorReadLine();
  var until=DateTime.UtcNow.AddSeconds(30);
  while(DateTime.UtcNow<until){if(Owned.HasExited)throw new Exception("LUMINA backend exited with code "+Owned.ExitCode+".\n"+Diagnostics);if(await Healthy())return;await Task.Delay(200);}
  throw new Exception("LUMINA did not become healthy within 30 seconds.\n"+Diagnostics);
 }
 void Record(string? s){if(s==null)return;lock(this){Diagnostics=(Diagnostics+"\n"+s);if(Diagnostics.Length>8000)Diagnostics=Diagnostics[^8000..];}}
 public async Task<bool> Healthy(){try{using var r=await http.GetAsync(Origin+"/health");if(!r.IsSuccessStatusCode)return false;var j=JsonDocument.Parse(await r.Content.ReadAsStringAsync()).RootElement;return j.GetProperty("application").GetString()=="LUMINA"&&j.GetProperty("api_version").GetInt32()==1&&j.GetProperty("status").GetString()=="ready";}catch{return false;}}
 public void Dispose(){if(Owned!=null){try{if(!Owned.HasExited){Owned.StandardInput.WriteLine("shutdown");Owned.StandardInput.Close();if(!Owned.WaitForExit(8000))Owned.Kill(true);}}catch{}Owned.Dispose();}http.Dispose();}
}
sealed class MainWindow:DarkForm {
 readonly Backend backend;readonly WebView2 view=new(){Dock=DockStyle.Fill,DefaultBackgroundColor=ShellTheme.Background};
 readonly Label surface=new(){Dock=DockStyle.Fill,BackColor=ShellTheme.Background,ForeColor=ShellTheme.Foreground,TextAlign=ContentAlignment.MiddleCenter,Padding=new Padding(32),Text="Starting LUMINA..."};
 string runtimeVersion="unavailable";readonly System.Windows.Forms.Timer timer=new(){Interval=3000};bool checking,failed,microphone=true,microphoneConsent;
 readonly string? verification;
 public MainWindow(Backend b,string? verificationPath=null){verification=verificationPath;backend=b;Text="LUMINA";Width=1440;Height=950;Icon=Icon.ExtractAssociatedIcon(Environment.ProcessPath!);var menu=new MenuStrip(){BackColor=ShellTheme.Background,ForeColor=ShellTheme.Foreground,Renderer=new DarkMenuRenderer()};var app=new ToolStripMenuItem("LUMINA");app.DropDownItems.Add("Quit",null,(_,_)=>Close());var mic=new ToolStripMenuItem("Allow microphone requests (asks first)"){CheckOnClick=true,Checked=true};mic.CheckedChanged+=(_,_)=>{microphone=mic.Checked;microphoneConsent=false;if(view.CoreWebView2!=null)_=view.CoreWebView2.ExecuteScriptAsync("window.dispatchEvent(new CustomEvent('lumina-microphone-policy',{detail:{enabled:"+(microphone?"true":"false")+"}}));"+(!microphone?"document.getElementById('stop')?.click()":""));};app.DropDownItems.Add(mic);app.DropDownItems.Add("Microphone diagnostics",null,(_,_)=>DarkDialog.Show(Privacy(),"LUMINA microphone"));menu.Items.Add(app);Controls.Add(view);Controls.Add(surface);surface.BringToFront();Controls.Add(menu);MainMenuStrip=menu;Shown+=async(_,_)=>await Start();FormClosed+=(_,_)=>{timer.Stop();timer.Dispose();};}
 string Privacy(){var lines=new List<string>{"WebView2 Evergreen runtime: "+runtimeVersion,"WebView microphone policy: "+(microphone?"enabled (prompt on request)":"disabled"),"Win32 desktop application; a per-app Windows consent record may not exist."};foreach(var hive in new[]{Microsoft.Win32.Registry.CurrentUser,Microsoft.Win32.Registry.LocalMachine})foreach(var tail in new[]{"",@"\NonPackaged"}){using var k=hive.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"+tail);lines.Add(hive.Name+tail+": "+(k?.GetValue("Value")?.ToString()??"unknown"));}lines.Add("Unknown is not denied. Missing/busy devices and drivers require the in-app device test; Gemini errors are separate.");return string.Join("\n",lines);}
 bool Trusted(string url)=>Uri.TryCreate(url,UriKind.Absolute,out var u)&&u.GetLeftPart(UriPartial.Authority)==backend.Origin;
 async Task Start(){try{
  runtimeVersion=CoreWebView2Environment.GetAvailableBrowserVersionString();await backend.Initialize();if(IsDisposed)return;
  var env=await CoreWebView2Environment.CreateAsync(null,Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"LUMINA","WebView2"));await view.EnsureCoreWebView2Async(env);if(IsDisposed)return;runtimeVersion=env.BrowserVersionString;
  view.CoreWebView2.Profile.PreferredColorScheme=CoreWebView2PreferredColorScheme.Dark;
  view.CoreWebView2.Settings.IsBuiltInErrorPageEnabled=false;
  view.CoreWebView2.ProcessFailed+=(_,e)=>ShowFailure("WebView2 stopped ("+e.ProcessFailedKind+"). Close and reopen LUMINA to retry deliberately.");
  view.CoreWebView2.Settings.AreDevToolsEnabled=false;view.CoreWebView2.Settings.AreHostObjectsAllowed=false;view.CoreWebView2.Settings.IsWebMessageEnabled=false;
  view.CoreWebView2.NavigationStarting+=(_,e)=>{if(!Trusted(e.Uri)){e.Cancel=true;External(e.Uri);}};
  view.CoreWebView2.FrameNavigationStarting+=(_,e)=>{if(!Trusted(e.Uri))e.Cancel=true;};
  view.CoreWebView2.NewWindowRequested+=(_,e)=>{e.Handled=true;External(e.Uri);};
  view.CoreWebView2.PermissionRequested+=PermissionRequested;
  view.CoreWebView2.NavigationCompleted+=async(_,e)=>{if(failed||IsDisposed)return;if(!e.IsSuccess){ShowFailure("LUMINA could not load ("+e.WebErrorStatus+"). Close and reopen to retry deliberately.");return;}surface.Visible=false;if(verification!=null&&e.IsSuccess)await VerifyWindow();};
  view.CoreWebView2.Navigate(backend.Origin);timer.Tick+=async(_,_)=>{if(checking||failed)return;checking=true;try{if(!await backend.Healthy()){ShowFailure("The local server stopped or became unhealthy. No automatic restart was attempted.\nClose and reopen LUMINA to retry deliberately.");}}finally{checking=false;}};timer.Start();
 }catch(Exception e){if(IsDisposed)return;if(verification!=null){File.WriteAllText(verification,JsonSerializer.Serialize(new{ok=false,error=e.Message}));Close();return;}ShowFailure("LUMINA could not start.\n"+e.Message+"\nVerify runtime.json, Python dependencies and Evergreen WebView2 Runtime.\nDetected runtime: "+runtimeVersion);}}
 async Task VerifyWindow(){
  try{
   await Task.Delay(5000);
   var content=await view.CoreWebView2.ExecuteScriptAsync("JSON.stringify({title:document.title,health:document.getElementById('runtime-health')?.textContent,graphNodes:document.getElementById('graph')?.dataset.nodeCount,graphRenderer:document.getElementById('graph')?.dataset.renderer,graphCanvas:!!document.querySelector('#graph canvas'),micWidth:document.getElementById('mic')?.getBoundingClientRect().width,sendWidth:document.querySelector('.send')?.getBoundingClientRect().width,notice:document.getElementById('notice')?.textContent})");
   using(var output=File.Create(verification+".png"))await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,output);
   File.WriteAllText(verification!,JsonSerializer.Serialize(new{ok=true,visible=Visible,content,webview=runtimeVersion,origin=backend.Origin,owned=backend.Owned!=null}));
  }catch(Exception e){File.WriteAllText(verification!,JsonSerializer.Serialize(new{ok=false,error=e.Message}));}
  Close();
 }
 void PermissionRequested(object? sender,CoreWebView2PermissionRequestedEventArgs e){
  e.SavesInProfile=false;e.State=CoreWebView2PermissionState.Deny;
  if(!Trusted(e.Uri)||!Trusted(view.CoreWebView2.Source))return;
  // Playback is controlled by LUMINA's spoken-replies setting; this grants no capture.
  if(e.PermissionKind==CoreWebView2PermissionKind.Autoplay){e.State=CoreWebView2PermissionState.Allow;return;}
  if(!microphone||e.PermissionKind!=CoreWebView2PermissionKind.Microphone)return;
  if(microphoneConsent){e.State=CoreWebView2PermissionState.Allow;return;}
  var deferral=e.GetDeferral();
  // Post the modal prompt after the WebView callback returns to avoid reentrancy.
  BeginInvoke((Action)(()=>{
   try{
    if(IsDisposed||!microphone||!Trusted(e.Uri)||!Trusted(view.CoreWebView2.Source))return;
    microphoneConsent=DarkDialog.Show("Allow LUMINA to access your microphone when you use Talk or audio settings?\nDevice discovery is a brief local check. Audio is sent to your configured provider only during a voice call.\nThis permission lasts until this window closes or you disable microphone requests in the LUMINA menu.","LUMINA microphone access",MessageBoxButtons.YesNo)==DialogResult.Yes;
    if(microphoneConsent&&microphone&&Trusted(view.CoreWebView2.Source))e.State=CoreWebView2PermissionState.Allow;
   }finally{deferral.Complete();}
  }));
 }
 void ShowFailure(string message){if(IsDisposed)return;failed=true;timer.Stop();view.Visible=false;surface.Text=message;surface.Visible=true;surface.BringToFront();if(verification!=null){File.WriteAllText(verification,JsonSerializer.Serialize(new{ok=false,error=message,webview=runtimeVersion}));Close();}}
 void External(string url){if(Uri.TryCreate(url,UriKind.Absolute,out var u)&&u.Scheme is "https" or "http"&&DarkDialog.Show("Open this external address in your browser?\n"+url,"LUMINA",MessageBoxButtons.YesNo)==DialogResult.Yes)Process.Start(new ProcessStartInfo(url){UseShellExecute=true});}
}

// Use documented per-window DWM attributes; never alter Windows theme or security settings.
static class ShellTheme {
 public static readonly Color Background=Color.FromArgb(8,9,11),Foreground=Color.FromArgb(230,231,235),Highlight=Color.FromArgb(38,39,44);
 [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr window,int attribute,ref int value,int size);
 public static void Apply(IntPtr window){
  int dark=1,background=0x0b0908,foreground=0xebe7e6;
  _=DwmSetWindowAttribute(window,20,ref dark,4);
  // Windows 11 supports exact caption/border colors; older versions ignore these attributes.
  _=DwmSetWindowAttribute(window,34,ref background,4);
  _=DwmSetWindowAttribute(window,35,ref background,4);
  _=DwmSetWindowAttribute(window,36,ref foreground,4);
 }
}
class DarkForm:Form {
 public DarkForm(){BackColor=ShellTheme.Background;ForeColor=ShellTheme.Foreground;}
 protected override void OnHandleCreated(EventArgs e){base.OnHandleCreated(e);ShellTheme.Apply(Handle);}
 protected override void WndProc(ref Message m){base.WndProc(ref m);if(m.Msg is 0x001C or 0x031A or 0x0320)ShellTheme.Apply(Handle);}
}
sealed class DarkMenuColors:ProfessionalColorTable {
 public DarkMenuColors(){UseSystemColors=false;}
 public override Color ToolStripDropDownBackground=>ShellTheme.Background;
 public override Color ImageMarginGradientBegin=>ShellTheme.Background;
 public override Color ImageMarginGradientMiddle=>ShellTheme.Background;
 public override Color ImageMarginGradientEnd=>ShellTheme.Background;
 public override Color MenuBorder=>ShellTheme.Background;
 public override Color MenuItemBorder=>ShellTheme.Highlight;
 public override Color MenuItemSelected=>ShellTheme.Highlight;
 public override Color MenuItemSelectedGradientBegin=>ShellTheme.Highlight;
 public override Color MenuItemSelectedGradientEnd=>ShellTheme.Highlight;
 public override Color MenuItemPressedGradientBegin=>ShellTheme.Highlight;
 public override Color MenuItemPressedGradientMiddle=>ShellTheme.Highlight;
 public override Color MenuItemPressedGradientEnd=>ShellTheme.Highlight;
 public override Color CheckBackground=>ShellTheme.Highlight;
 public override Color CheckSelectedBackground=>ShellTheme.Highlight;
 public override Color CheckPressedBackground=>ShellTheme.Highlight;
}
sealed class DarkMenuRenderer:ToolStripProfessionalRenderer {
 public DarkMenuRenderer():base(new DarkMenuColors()){RoundedEdges=false;}
 protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e){e.TextColor=ShellTheme.Foreground;base.OnRenderItemText(e);}
 protected override void OnRenderArrow(ToolStripArrowRenderEventArgs e){e.ArrowColor=ShellTheme.Foreground;base.OnRenderArrow(e);}
 protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e){}
}
static class DarkDialog {
 public static DialogResult Show(string message,string title,MessageBoxButtons buttons=MessageBoxButtons.OK,MessageBoxIcon icon=MessageBoxIcon.None){
  using var dialog=new DarkForm{Text=title,ClientSize=new Size(620,320),MinimumSize=new Size(420,240),StartPosition=FormStartPosition.CenterParent,ShowInTaskbar=false,MinimizeBox=false,MaximizeBox=false};
  var text=new TextBox{Multiline=true,ReadOnly=true,BorderStyle=BorderStyle.None,BackColor=ShellTheme.Background,ForeColor=ShellTheme.Foreground,Dock=DockStyle.Fill,ScrollBars=ScrollBars.Vertical,Text=message.Replace("\n",Environment.NewLine)};
  var content=new Panel{Dock=DockStyle.Fill,Padding=new Padding(24)};content.Controls.Add(text);
  var actions=new FlowLayoutPanel{Dock=DockStyle.Bottom,Height=56,FlowDirection=FlowDirection.RightToLeft,Padding=new Padding(8)};
  Button Add(string label,DialogResult result){var button=new Button{Text=label,DialogResult=result,FlatStyle=FlatStyle.Flat,BackColor=ShellTheme.Background,ForeColor=ShellTheme.Foreground,Size=new Size(96,32)};button.FlatAppearance.BorderColor=ShellTheme.Highlight;actions.Controls.Add(button);return button;}
  if(buttons==MessageBoxButtons.YesNo){dialog.CancelButton=Add("No",DialogResult.No);Add("Yes",DialogResult.Yes);dialog.AcceptButton=(IButtonControl)dialog.CancelButton;}
  else{var ok=Add("OK",DialogResult.OK);dialog.AcceptButton=ok;dialog.CancelButton=ok;}
  dialog.Controls.Add(content);dialog.Controls.Add(actions);return dialog.ShowDialog(Form.ActiveForm);
 }
}
