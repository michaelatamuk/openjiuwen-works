Add-Type -AssemblyName System.Speech
$dir = "C:\Workspace\openjiuwenothers\factory\video_audio"
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$lines = @(
  "Berlin, Monday, nine a.m. A customer opens an invoice: 21% V A T. It should be 19%.",
  "Today, that fix takes four days. A queue. An agent waiting for answers. A reviewer waiting for time.",
  "Almost none of it is writing code.",
  "Now the same Monday, again.",
  "Three ways in: a failure caught in the app, a bug already filed, a person reporting it.",
  "The engine reads the code, drafts a plan, and stops. The developer approves it. One click.",
  "It builds in its own sandbox. A second agent checks it, with tests the first never saw.",
  "No diff to read. One page: what changed, what was tested, what it cost.",
  "One more click. The fix ships.",
  "And it goes back where the bug was seen: the invoice is correct, the ticket closes, the customer gets a reply.",
  "Nothing was forked. jiuwenswarm builds, agent-core checks, P P M A remembers.",
  "openJiuwen Works. The waiting moved. The judgement stayed."
)

for ($i = 0; $i -lt $lines.Count; $i++) {
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice('Microsoft Zira Desktop')
  $s.Rate = -1
  $s.Volume = 100
  $n = "{0:D2}" -f ($i + 1)
  $s.SetOutputToWaveFile("$dir\v$n.wav")
  $s.Speak($lines[$i])
  $s.Dispose()
}
Get-ChildItem $dir -Filter *.wav | Select-Object Name, Length
