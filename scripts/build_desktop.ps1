param([ValidateSet('Development','Portable')][string]$Mode='Development',[switch]$AllowUnsigned,[string]$SigningThumbprint,[string]$OutputDirectory,[switch]$IncludePersonalKnowledge)
$ErrorActionPreference='Stop'
if(-not $SigningThumbprint -and -not $AllowUnsigned){throw 'Supply -SigningThumbprint for a trusted certificate or -AllowUnsigned explicitly for a zero-cost unsigned build.'}
if(-not $SigningThumbprint){Write-Warning 'UNSIGNED build: not production-trusted; SmartScreen may warn. No certificate or Windows security changes will be made.'}
$root=Split-Path $PSScriptRoot -Parent
# Always create a new package. Never refresh an existing install/config/profile in place.
$dist=[IO.Path]::GetFullPath((Join-Path $root 'dist'))
if(-not $OutputDirectory){$OutputDirectory=Join-Path $dist ("LUMINA-$Mode-"+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8))}
$absolute=$OutputDirectory -match '^(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+)'
if([IO.Path]::IsPathRooted($OutputDirectory) -and -not $absolute){throw 'OutputDirectory must be fully absolute or relative beneath repo dist.'}
$out=if($absolute){[IO.Path]::GetFullPath($OutputDirectory)}else{[IO.Path]::GetFullPath((Join-Path $root $OutputDirectory))}
if(-not $absolute -and -not $out.StartsWith($dist+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Relative OutputDirectory must be beneath repo dist.'}
# Reject junction/symlink ancestors, including dangling reparse points.
$ancestor=$out
while($ancestor){
 if(Test-Path -LiteralPath $ancestor){if((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'OutputDirectory cannot traverse a reparse point.'}}
 $ancestor=Split-Path $ancestor -Parent
}
if(Test-Path -LiteralPath $out){throw 'OutputDirectory already exists. Select a NEW directory; existing packages and user data are never overwritten.'}
New-Item -ItemType Directory -Path $out | Out-Null
Add-Type -AssemblyName System.Drawing
$sizes=@(16,24,32,48,64,128,256)
$images=@()
foreach($size in $sizes){
 $bmp=[System.Drawing.Bitmap]::new($size,$size);$g=[System.Drawing.Graphics]::FromImage($bmp);$g.SmoothingMode='AntiAlias';$g.Clear([System.Drawing.Color]::FromArgb(8,9,11))
 $brush=[System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(240,113,141));$g.FillEllipse($brush,$size*.16,$size*.16,$size*.68,$size*.68)
 $pen=[System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(255,220,232),[single]($size*.055));$g.DrawEllipse($pen,$size*.24,$size*.24,$size*.52,$size*.52)
 $ms=[IO.MemoryStream]::new();$bmp.Save($ms,[System.Drawing.Imaging.ImageFormat]::Png);$images+=,@($ms.ToArray());$g.Dispose();$bmp.Dispose();$brush.Dispose();$pen.Dispose();$ms.Dispose()
}
$ico=Join-Path $out 'lumina.ico';$fs=[IO.File]::Create($ico);$writer=[IO.BinaryWriter]::new($fs);$writer.Write([uint16]0);$writer.Write([uint16]1);$writer.Write([uint16]$sizes.Count);$offset=6+16*$sizes.Count
for($i=0;$i -lt $sizes.Count;$i++){ $s=$sizes[$i];$dim=if($s -eq 256){0}else{$s};$writer.Write([byte]$dim);$writer.Write([byte]$dim);$writer.Write([uint16]0);$writer.Write([uint16]1);$writer.Write([uint16]32);$writer.Write([uint32]$images[$i].Length);$writer.Write([uint32]$offset);$offset+=$images[$i].Length }
foreach($bytes in $images){$writer.Write([byte[]]$bytes)};$writer.Dispose()
dotnet publish (Join-Path $root 'desktop/LUMINA.csproj') -c Release -r win-x64 --self-contained true -p:ApplicationIcon=$ico -o $out
if($LASTEXITCODE){throw 'Desktop compilation failed.'}
dotnet publish (Join-Path $root 'camera-helper/LUMINA.Camera.csproj') -c Release -r win-x64 --self-contained true -o (Join-Path $out 'camera')
if($LASTEXITCODE){throw 'Camera helper compilation failed.'}
if($Mode -eq 'Portable'){
 $app=Join-Path $out 'app';New-Item -ItemType Directory -Force $app | Out-Null
 foreach($folder in @('lumina','web')){
  $source=Join-Path $root $folder
  Get-ChildItem -LiteralPath $source -File -Recurse | Where-Object { $_.Extension -ne '.pyc' -and $_.FullName -notmatch '[\\/]__pycache__[\\/]' } | ForEach-Object {
   $target=Join-Path (Join-Path $app $folder) $_.FullName.Substring($source.Length+1)
   New-Item -ItemType Directory -Force (Split-Path $target -Parent) | Out-Null
   Copy-Item -LiteralPath $_.FullName -Destination $target -Force
  }
 }
 Copy-Item -LiteralPath (Join-Path $root '.env.example') -Destination (Join-Path $app '.env.example')
 Copy-Item -LiteralPath (Join-Path $root 'lumina.example.toml') -Destination (Join-Path $app 'lumina.toml')
 if($IncludePersonalKnowledge){
  & (Join-Path $root '.venv/Scripts/python.exe') (Join-Path $root 'scripts/package_knowledge.py') $root $app
  if($LASTEXITCODE){throw 'Personal knowledge packaging failed.'}
 }
 $runtime=Join-Path $out 'python';New-Item -ItemType Directory -Force $runtime | Out-Null
 $archive=Join-Path $out 'python-embed.zip'
 Invoke-WebRequest 'https://www.python.org/ftp/python/3.13.9/python-3.13.9-embed-amd64.zip' -OutFile $archive
 Expand-Archive -LiteralPath $archive -DestinationPath $runtime -Force
 @('python313.zip','.','Lib/site-packages','../app','import site') | Set-Content (Join-Path $runtime 'python313._pth')
 & (Join-Path $root '.venv/Scripts/python.exe') -m pip install --no-compile --target (Join-Path $runtime 'Lib/site-packages') -r (Join-Path $root 'requirements.txt') -r (Join-Path $root 'requirements-phase1.txt')
 if($LASTEXITCODE){throw 'Portable dependencies failed.'}
 $previousBrowserPath=$env:PLAYWRIGHT_BROWSERS_PATH
 try{
  $env:PLAYWRIGHT_BROWSERS_PATH=(Join-Path $out 'playwright-browsers')
  & (Join-Path $runtime 'python.exe') -m playwright install chromium
  if($LASTEXITCODE){Write-Warning 'Playwright Chromium was not bundled; browser control will report unavailable until installed.'}
 }finally{$env:PLAYWRIGHT_BROWSERS_PATH=$previousBrowserPath}
 $meta=@{mode=$Mode;root='app';python='python/python.exe';entry_point='lumina/desktop_backend.py';web='web';config='lumina.toml'}
}else{$meta=@{mode=$Mode;root=$root;python=(Join-Path $root '.venv/Scripts/python.exe');entry_point='lumina/desktop_backend.py';web='web';config='lumina.toml'}}
$meta | ConvertTo-Json | Set-Content (Join-Path $out 'runtime.json')
$exe=Join-Path $out 'LUMINA.exe'
if($SigningThumbprint){
 $cert=Get-Item -LiteralPath "Cert:\CurrentUser\My\$SigningThumbprint"
 if(-not $cert.HasPrivateKey -or -not ($cert.EnhancedKeyUsageList.ObjectId -contains '1.3.6.1.5.5.7.3.3')){throw 'The certificate must have a private key and code-signing usage.'}
 $chain=[Security.Cryptography.X509Certificates.X509Chain]::new()
 if(-not $chain.Build($cert)){throw 'The signing certificate is not trusted or valid. No trust settings were changed.'}
 Set-AuthenticodeSignature -LiteralPath $exe -Certificate $cert -HashAlgorithm SHA256 | Out-Null
 Set-AuthenticodeSignature -LiteralPath (Join-Path $out 'camera/LUMINA.Camera.exe') -Certificate $cert -HashAlgorithm SHA256 | Out-Null
 if((Get-AuthenticodeSignature -LiteralPath (Join-Path $out 'camera/LUMINA.Camera.exe')).Status -ne 'Valid'){throw 'Camera signature verification failed.'}
 if((Get-AuthenticodeSignature -LiteralPath $exe).Status -ne 'Valid'){throw 'Signature verification failed.'}
}
$signature=Get-AuthenticodeSignature -LiteralPath $exe
[pscustomobject]@{Executable=$exe;Root=$meta.root;Python=$meta.python;Signing=$signature.Status;SigningIdentity=$signature.SignerCertificate.Subject;Microphone='Requires user-enabled live device check';ServerCheck='Pending launcher acceptance';WebView2='Validated on launch'} | Format-List

# Safe diagnostics: versions, relative package paths and public signing metadata only.
# Do not serialize environment variables, config contents, credentials or certificate keys.
[xml]$project=Get-Content -LiteralPath (Join-Path $root 'desktop/LUMINA.csproj')
$webviewSdk=($project.Project.ItemGroup.PackageReference | Where-Object Include -eq 'Microsoft.Web.WebView2').Version
$runtimeVersion='unavailable'
try{
 $loader=(Join-Path $out 'WebView2Loader.dll').Replace('"','""')
 $probeType='LuminaWebViewVersion'+[Guid]::NewGuid().ToString('N')
 Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class $probeType {
 [DllImport(@"$loader", CharSet=CharSet.Unicode)]
 public static extern int GetAvailableCoreWebView2BrowserVersionString(string folder, out IntPtr version);
}
"@
 $versionPointer=[IntPtr]::Zero
 try{
  $result=($probeType -as [type])::GetAvailableCoreWebView2BrowserVersionString($null,[ref]$versionPointer)
  [Runtime.InteropServices.Marshal]::ThrowExceptionForHR($result)
  $runtimeVersion=[Runtime.InteropServices.Marshal]::PtrToStringUni($versionPointer)
 }finally{if($versionPointer -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::FreeCoTaskMem($versionPointer)}}
}catch{Write-Warning 'Evergreen WebView2 Runtime could not be detected; install/update the official Evergreen Runtime before launch.'}
$signing=@(foreach($relative in @('LUMINA.exe','camera/LUMINA.Camera.exe')){
 $signedFile=Join-Path $out $relative
 $sig=Get-AuthenticodeSignature -LiteralPath $signedFile
 [ordered]@{file=$relative;status=$sig.Status.ToString();subject=$sig.SignerCertificate.Subject;thumbprint=$sig.SignerCertificate.Thumbprint;timestamped=($null -ne $sig.TimeStamperCertificate);sha256=(Get-FileHash -LiteralPath $signedFile -Algorithm SHA256).Hash}
})
$pythonExe=if($Mode -eq 'Portable'){Join-Path $out 'python/python.exe'}else{Join-Path $root '.venv/Scripts/python.exe'}
$pythonVersion=(& $pythonExe --version 2>&1 | Out-String).Trim()
if($LASTEXITCODE){throw 'Python version diagnostics failed.'}
$dependencyProbe='import importlib.metadata as m,json; print(json.dumps(sorted([{"name":d.metadata["Name"],"version":d.version} for d in m.distributions()],key=lambda d:d["name"].lower())))'
$dependenciesJson=$dependencyProbe | & $pythonExe -
if($LASTEXITCODE){throw 'Python dependency diagnostics failed.'}
$assets=@(foreach($folder in @('lumina','web')){
 $source=if($Mode -eq 'Portable'){Join-Path $out "app/$folder"}else{Join-Path $root $folder}
 Get-ChildItem -LiteralPath $source -File -Recurse | Where-Object {$_.Extension -ne '.pyc' -and $_.FullName -notmatch '[\\/]__pycache__[\\/]'} | ForEach-Object {
  [ordered]@{file=$folder+'/'+$_.FullName.Substring($source.Length+1).Replace('\','/');sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}
 }
})
[ordered]@{
 schema=1;builtUtc=[DateTime]::UtcNow.ToString('o');mode=$Mode
 applicationVersion=[string]$project.Project.PropertyGroup.Version.Where({$_})[0]
 dotnetSdk=(& dotnet --version | Out-String).Trim();target='net10.0-windows';architecture='win-x64'
 webview2=[ordered]@{sdk=[string]$webviewSdk;distribution='Evergreen (installed separately)';detectedRuntime=$runtimeVersion;actualRuntime='Reported at launch in microphone diagnostics and window verification'}
 python=$pythonVersion;dependencies=@($dependenciesJson | ConvertFrom-Json)
 unsignedExplicitlyAllowed=[bool]$AllowUnsigned;signing=$signing;assets=$assets
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $out 'build-manifest.json') -Encoding UTF8
Write-Output "New package: $out"
Write-Output "WebView2 SDK: $webviewSdk; detected Evergreen Runtime: $runtimeVersion"
