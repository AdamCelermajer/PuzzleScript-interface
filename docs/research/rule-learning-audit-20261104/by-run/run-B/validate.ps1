$ErrorActionPreference='Stop'
$out=Join-Path $PSScriptRoot 'independent-labels.json'
$root=Resolve-Path (Join-Path $PSScriptRoot '../../../../..')
$all=Get-Content (Join-Path $root 'docs/research/rule-learning-audit-20261104/inventory.json') -Raw|ConvertFrom-Json
$inventory=@($all | Where-Object run -eq 'run-B')
$labels=Get-Content $out -Raw|ConvertFrom-Json
$issues=@(); $quotes=@(); $counts=@{}
foreach($entry in $labels){
 $expected=$inventory|Where-Object cp -eq $entry.cp
 $actual=@($entry.labels.PSObject.Properties.Name)
 if(@(Compare-Object @($expected.rules) $actual).Count){$issues+="Rule coverage cp $($entry.cp)"}
 foreach($r in $entry.labels.PSObject.Properties){
  $v=$r.Value; $counts[$v.belief]++
  if($v.note -match '^[NT]: '){
   $quote=$v.note.Substring(3)
   $ev=$inventory|Where-Object cp -eq $v.evidence_cp
   $text=Get-Content (Join-Path $root $ev.path) -Raw -Encoding utf8
   $pos=$text.IndexOf($quote,[StringComparison]::Ordinal)
   if($pos -lt 0){$issues+="Quote mismatch cp $($entry.cp) $($r.Name)"}
   if(($quote -split '\s+').Count -gt 20){$issues+="Quote too long cp $($entry.cp) $($r.Name)"}
   $line=if($pos -ge 0){($text.Substring(0,$pos) -split "`n").Count}else{$null}
   $quotes+=@{cp=$entry.cp;rule=$r.Name;evidence_cp=$v.evidence_cp;path=$ev.path;line=$line;quote=$quote;exact_match=($pos -ge 0)}
  }
 }
}
$missing=@($inventory|Where-Object {$_.cp -notin $labels.cp}|ForEach-Object cp)
$result=@{status='INCOMPLETE';expected_checkpoints=$inventory.Count;reviewed_checkpoints=$labels.Count;reviewed_slots=($labels.Count*7);unreviewed_checkpoints=$missing;unreviewed_slots=($missing.Count*7);label_counts=$counts;issues=$issues;quote_matches=$quotes;frozen=$false;comparison_performed=$false}
$result|ConvertTo-Json -Depth 12|Set-Content (Join-Path $PSScriptRoot 'validation.json') -Encoding utf8
$result|Select-Object status,expected_checkpoints,reviewed_checkpoints,reviewed_slots,unreviewed_slots,issues|ConvertTo-Json



