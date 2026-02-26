$duration = 600
$interval = 5

$logfile = "../logs/mtn/mtn_log_" + (Get-Date -Format "yyyyMMdd_HHmm") + ".txt"

$targets = @("8.8.8.8","1.1.1.1","google.com")

Add-Content $logfile "START MTN TEST"
Add-Content $logfile (Get-Date)

$latencies = @()
$loss = 0
$start = Get-Date

while ((New-TimeSpan -Start $start).TotalSeconds -lt $duration) {

    foreach ($target in $targets) {

        try {
            $resp = Test-Connection $target -Count 1 -ErrorAction Stop
            $latencies += $resp.ResponseTime
            Add-Content $logfile "OK $target $($resp.ResponseTime) ms"
        }
        catch {
            $loss++
            Add-Content $logfile "LOSS $target"
        }
    }

    Start-Sleep $interval
}

if ($latencies.Count -gt 0) {

    $avg = ($latencies | Measure-Object -Average).Average
    $max = ($latencies | Measure-Object -Maximum).Maximum
    $min = ($latencies | Measure-Object -Minimum).Minimum

    Add-Content $logfile "AVG=$avg"
    Add-Content $logfile "MAX=$max"
    Add-Content $logfile "MIN=$min"
}

Add-Content $logfile "PACKET LOSS=$loss"
Add-Content $logfile "END MTN TEST"