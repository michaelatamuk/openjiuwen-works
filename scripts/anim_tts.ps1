Add-Type -AssemblyName System.Speech
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$dir = Join-Path $root 'docs\frames'
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Zira Desktop')
$s.Rate = -1
$s.SetOutputToWaveFile((Join-Path $dir 'a1.wav'))
$s.Speak('Four days. Or one hour, forty five.')
$s.SetOutputToWaveFile((Join-Path $dir 'a2.wav'))
$s.Speak('openJiuwen Works. The waiting moved. The judgement stayed.')
$s.Dispose()
Get-ChildItem (Join-Path $dir 'a*.wav') | Select-Object Name, Length
