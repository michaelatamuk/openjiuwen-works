Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Zira Desktop')
$s.Rate = -1
$s.SetOutputToWaveFile('C:\Workspace\openjiuwenothers\factory\anim\a1.wav')
$s.Speak('Four days. Or one hour, forty five.')
$s.SetOutputToWaveFile('C:\Workspace\openjiuwenothers\factory\anim\a2.wav')
$s.Speak('openJiuwen Works. The waiting moved. The judgement stayed.')
$s.Dispose()
Get-ChildItem 'C:\Workspace\openjiuwenothers\factory\anim\a*.wav' | Select-Object Name, Length
