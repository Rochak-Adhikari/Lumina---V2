# Compile-time fixed Core Audio interfaces. Never changes default endpoints.
Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
[ComImport,Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class LuminaEnumerator {}
[ComImport,Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface ILuminaEnumerator {
 [PreserveSig] int EnumAudioEndpoints(int flow,uint mask,out ILuminaCollection devices);
 [PreserveSig] int GetDefaultAudioEndpoint(int flow,int role,out ILuminaDevice device);
 [PreserveSig] int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string id,out ILuminaDevice device);
}
[ComImport,Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface ILuminaCollection {
 [PreserveSig] int GetCount(out uint count); [PreserveSig] int Item(uint n,out ILuminaDevice device);
}
[ComImport,Guid("D666063F-1587-4E43-81F1-B948E807363F"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface ILuminaDevice {
 [PreserveSig] int Activate(ref Guid iid,uint ctx,IntPtr parameters,[MarshalAs(UnmanagedType.IUnknown)]out object obj);
 [PreserveSig] int OpenPropertyStore(uint mode,out IntPtr store);
 [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)]out string id); [PreserveSig] int GetState(out uint state);
}
[ComImport,Guid("5CDF2C82-841E-4546-9722-0CF74078229A"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface ILuminaVolume {
 [PreserveSig] int RegisterControlChangeNotify(IntPtr p); [PreserveSig] int UnregisterControlChangeNotify(IntPtr p);
 [PreserveSig] int GetChannelCount(out uint count); [PreserveSig] int SetMasterVolumeLevel(float level,ref Guid context);
 [PreserveSig] int SetMasterVolumeLevelScalar(float level,ref Guid context); [PreserveSig] int GetMasterVolumeLevel(out float level);
 [PreserveSig] int GetMasterVolumeLevelScalar(out float level); [PreserveSig] int SetChannelVolumeLevel(uint channel,float level,ref Guid context);
 [PreserveSig] int SetChannelVolumeLevelScalar(uint channel,float level,ref Guid context); [PreserveSig] int GetChannelVolumeLevel(uint channel,out float level);
 [PreserveSig] int GetChannelVolumeLevelScalar(uint channel,out float level); [PreserveSig] int SetMute([MarshalAs(UnmanagedType.Bool)]bool mute,ref Guid context);
 [PreserveSig] int GetMute([MarshalAs(UnmanagedType.Bool)]out bool mute);
}
public static class LuminaAudio {
 static void Check(int hr) { Marshal.ThrowExceptionForHR(hr); }
 public static object[] List() {
  var e=(ILuminaEnumerator)new LuminaEnumerator(); ILuminaCollection c=null;
  try { Check(e.EnumAudioEndpoints(2,15,out c)); uint n; Check(c.GetCount(out n)); var rows=new List<object>();
   for(uint i=0;i<n && i<256;i++){ ILuminaDevice d=null; try {Check(c.Item(i,out d));string id;uint state;Check(d.GetId(out id));Check(d.GetState(out state));rows.Add(new {id=id,state=state,connected=state==1});}finally{if(d!=null)Marshal.ReleaseComObject(d);} }
   return rows.ToArray();
  }finally{if(c!=null)Marshal.ReleaseComObject(c);Marshal.ReleaseComObject(e);}
 }
 public static object Read(string id) {return Access(id,false,0,false);}
 public static object Write(string id,float volume,bool mute) {return Access(id,true,volume,mute);}
 static object Access(string id,bool write,float volume,bool mute) {
  var e=(ILuminaEnumerator)new LuminaEnumerator(); ILuminaDevice d=null;object obj=null;
  try {Check(e.GetDevice(id,out d));uint state;Check(d.GetState(out state));if(state!=1)throw new InvalidOperationException("disconnected_endpoint");
   var guid=new Guid("5CDF2C82-841E-4546-9722-0CF74078229A");Check(d.Activate(ref guid,23,IntPtr.Zero,out obj));var v=(ILuminaVolume)obj;
   if(write){if(volume<0 || volume>1 || float.IsNaN(volume))throw new Exception();var context=Guid.Empty;Check(v.SetMasterVolumeLevelScalar(volume,ref context));Check(v.SetMute(mute,ref context));}
   float actual;bool muted;Check(v.GetMasterVolumeLevelScalar(out actual));Check(v.GetMute(out muted));return new {identity=id,value=new {volume=actual,mute=muted}};
  }finally{if(obj!=null)Marshal.ReleaseComObject(obj);if(d!=null)Marshal.ReleaseComObject(d);Marshal.ReleaseComObject(e);}
 }
}
"@


