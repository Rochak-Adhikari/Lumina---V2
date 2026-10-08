using System.Diagnostics;
using System.Text.Json;
using Windows.Devices.Enumeration;
using Windows.Graphics.Imaging;
using Windows.Media.Capture;
using Windows.Media.Capture.Frames;
using Windows.Media.MediaProperties;
using Windows.Storage.Streams;

// One request, one process, one camera lifetime. No network listener or host bridge.
class Program {
 static readonly string Spool=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"LUMINA","camera");
 static async Task Main(string[] args) {
  if(args.Length!=1 || !Guid.TryParseExact(args[0],"N",out _))return;
  string id=args[0], request=Path.Combine(Spool,id+".request.json"), response=Path.Combine(Spool,id+".response.json");
  if(!File.Exists(request)||File.Exists(response))return;
  // An exclusive file handle also recovers automatically after either process crashes.
  // File locks recover automatically if a helper process terminates unexpectedly.
  FileStream? lease=null;
  try {
   lease=new FileStream(Path.Combine(Spool,"capture.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
   using var doc=JsonDocument.Parse(File.ReadAllText(request));
   if(doc.RootElement.GetProperty("id").GetString()!=id || doc.RootElement.GetProperty("expires").GetDouble()<DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()/1000.0)
    throw new InvalidOperationException("Capture request expired or is invalid.");
   var capture=Capture(id);
   var winner=await Task.WhenAny(capture,Task.Delay(TimeSpan.FromSeconds(18)));
   if(winner!=capture){Write(response,new{ok=false,id,error="Camera driver timed out; helper is exiting to release the device."});Environment.Exit(2);}
   var result=await capture;
   Write(response,result);
  } catch(UnauthorizedAccessException){Write(response,new{ok=false,id,error="Windows camera access was refused. Check camera privacy and desktop-app access."});}
    catch(Exception e){Write(response,new{ok=false,id,error=e is IOException?"Camera request is busy or its local files are unavailable.":e.Message});}
  finally{lease?.Dispose();}
 }
 static void Write(string path,object value){var temp=path+".tmp";File.WriteAllText(temp,JsonSerializer.Serialize(value));File.Move(temp,path,true);}
 static bool Virtual(string name)=>new[]{"obs","ecamm","elgato","virtual","snap camera","manycam","ndi"}.Any(name.ToLowerInvariant().Contains);
 static int Rank(DeviceInformation d)=>(d.EnclosureLocation!=null?100:0)+(new[]{"integrated","internal","built-in","builtin","front"}.Any(d.Name.ToLowerInvariant().Contains)?50:0);
 static async Task<object> Capture(string id){
  var devices=await DeviceInformation.FindAllAsync(DeviceClass.VideoCapture);
  var candidates=devices.Where(d=>d.IsEnabled&&!Virtual(d.Name)).OrderByDescending(Rank).ToArray();
  if(candidates.Length==0)throw new InvalidOperationException("No enabled physical camera was found; virtual cameras are excluded.");
  var errors=new List<string>();
  foreach(var device in candidates){
   try{return await CaptureDevice(id,device);}catch(UnauthorizedAccessException){throw;}
   catch(Exception e){errors.Add(device.Name+": "+e.Message);}
  }
  throw new InvalidOperationException("No camera produced a usable frame. "+string.Join("; ",errors));
 }
 static async Task<object> CaptureDevice(string id,DeviceInformation device){
  using var camera=new MediaCapture();
  await camera.InitializeAsync(new MediaCaptureInitializationSettings{VideoDeviceId=device.Id,StreamingCaptureMode=StreamingCaptureMode.Video,MemoryPreference=MediaCaptureMemoryPreference.Cpu,SharingMode=MediaCaptureSharingMode.ExclusiveControl});
  var source=camera.FrameSources.Values.FirstOrDefault(s=>s.Info.SourceKind==MediaFrameSourceKind.Color);
  if(source==null)throw new InvalidOperationException("Camera has no color frame source.");
  using var reader=await camera.CreateFrameReaderAsync(source,MediaEncodingSubtypes.Bgra8);
  if(await reader.StartAsync()!=MediaFrameReaderStartStatus.Success)throw new InvalidOperationException("Camera frame stream could not start.");
  try {
   var exposure=camera.VideoDeviceController.ExposureControl;
   bool auto=false;
   if(exposure.Supported){await exposure.SetAutoAsync(true);auto=exposure.Auto;}
   else {var basic=camera.VideoDeviceController.Exposure;auto=basic.Capabilities.AutoModeSupported&&basic.TrySetAuto(true);}
   // MediaCapture exposes Auto and Value, not an 'adjusting' state. Poll actual
   // exposure values on new frames as a bounded heuristic; never call it AE convergence.
   var clock=Stopwatch.StartNew();long? last=null;int stable=0;TimeSpan? timestamp=null;
   SoftwareBitmap? chosen=null;
   try {
    while(clock.Elapsed<TimeSpan.FromSeconds(3)){
     using var frame=reader.TryAcquireLatestFrame();
     if(frame?.VideoMediaFrame?.SoftwareBitmap is SoftwareBitmap bitmap && frame.SystemRelativeTime!=timestamp){
      timestamp=frame.SystemRelativeTime;
      chosen?.Dispose();chosen=SoftwareBitmap.Convert(bitmap,BitmapPixelFormat.Bgra8,BitmapAlphaMode.Ignore);
      if(exposure.Supported){long value=exposure.Value.Ticks;stable=last==value?stable+1:0;last=value;}
      if(!auto||!exposure.Supported||stable>=3)break;
     }
     await Task.Delay(30); // frame/state polling, not a fixed exposure warm-up
    }
    if(chosen==null)throw new InvalidOperationException("Camera delivered no frame within three seconds.");
    var pixels=new byte[chosen.PixelWidth*chosen.PixelHeight*4];
    var buffer=System.Runtime.InteropServices.WindowsRuntime.WindowsRuntimeBufferExtensions.AsBuffer(pixels);
    chosen.CopyToBuffer(buffer);
    long brightness=0;int samples=0;
    for(int i=0;i<pixels.Length;i+=64){brightness+=pixels[i]+pixels[i+1]+pixels[i+2];samples+=3;}
    if(samples==0||brightness/(double)samples<2)throw new InvalidOperationException("Camera returned a black frame; check its shutter, lighting or device source.");
    using var stream=new InMemoryRandomAccessStream();
    var encoder=await BitmapEncoder.CreateAsync(BitmapEncoder.JpegEncoderId,stream);encoder.SetSoftwareBitmap(chosen);await encoder.FlushAsync();
    if(stream.Size>16*1024*1024)throw new InvalidOperationException("Camera JPEG exceeds the capture size limit.");
    stream.Seek(0);using var data=new DataReader(stream);await data.LoadAsync((uint)stream.Size);byte[] jpeg=new byte[(int)stream.Size];data.ReadBytes(jpeg);
    string output=Path.Combine(Spool,id+".jpg");File.WriteAllBytes(output+".tmp",jpeg);File.Move(output+".tmp",output,true);
    return new{ok=true,id,device=device.Name,jpeg=id+".jpg",auto_exposure=auto,exposure_state="adjusting state unavailable in MediaCapture",exposure_value_stable=stable>=3,exposure_wait_ms=clock.ElapsedMilliseconds};
   }finally{chosen?.Dispose();}
  }finally{await reader.StopAsync();}
 }
}
