param(
    [Parameter(Mandatory = $true)]
    [string]$Profile,
    [string]$DisplayName = '',
    [string]$StateName = '',
    [switch]$TestChildOnly,
    [switch]$TestRestart,
    [int]$MaxConsecutiveRestarts = 5
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $DisplayName) { $DisplayName = $Profile }
if (-not $StateName) { $StateName = $Profile }
$StateRoot = Join-Path $env:LOCALAPPDATA 'Rex-Desktop-Bridge\state'
$StateDir = Join-Path $StateRoot $StateName
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$TunnelClient = Join-Path $Root 'tools\tunnel-client\tunnel-client.exe'

if (-not ('RdcKillJob' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class RdcKillJob
{
    public const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
    public const int JobObjectExtendedLimitInformation = 9;
    public const uint CREATE_SUSPENDED = 0x00000004;
    public const uint WAIT_OBJECT_0 = 0x00000000;
    public const uint INFINITE = 0xFFFFFFFF;

    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_BASIC_LIMIT_INFORMATION
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct IO_COUNTERS
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct STARTUPINFO
    {
        public uint cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public uint dwX;
        public uint dwY;
        public uint dwXSize;
        public uint dwYSize;
        public uint dwXCountChars;
        public uint dwYCountChars;
        public uint dwFillAttribute;
        public uint dwFlags;
        public ushort wShowWindow;
        public ushort cbReserved2;
        public IntPtr lpReserved2;
        public IntPtr hStdInput;
        public IntPtr hStdOutput;
        public IntPtr hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PROCESS_INFORMATION
    {
        public IntPtr hProcess;
        public IntPtr hThread;
        public uint dwProcessId;
        public uint dwThreadId;
    }

    public sealed class ChildProcess
    {
        public IntPtr ProcessHandle { get; private set; }
        public int ProcessId { get; private set; }
        public ChildProcess(IntPtr handle, int pid)
        {
            ProcessHandle = handle;
            ProcessId = pid;
        }
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr CreateJobObject(IntPtr lpJobAttributes, string lpName);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetInformationJobObject(IntPtr hJob, int JobObjectInfoClass, IntPtr lpJobObjectInfo, uint cbJobObjectInfoLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CreateProcess(
        string lpApplicationName,
        StringBuilder lpCommandLine,
        IntPtr lpProcessAttributes,
        IntPtr lpThreadAttributes,
        bool bInheritHandles,
        uint dwCreationFlags,
        IntPtr lpEnvironment,
        string lpCurrentDirectory,
        ref STARTUPINFO lpStartupInfo,
        out PROCESS_INFORMATION lpProcessInformation);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern uint ResumeThread(IntPtr hThread);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool CloseHandle(IntPtr hObject);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern uint WaitForSingleObject(IntPtr hHandle, uint dwMilliseconds);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetExitCodeProcess(IntPtr hProcess, out uint lpExitCode);

    public static IntPtr CreateKillOnCloseJob(string name)
    {
        IntPtr job = CreateJobObject(IntPtr.Zero, name);
        if (job == IntPtr.Zero)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "CreateJobObject failed");

        var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        int length = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
        IntPtr ptr = Marshal.AllocHGlobal(length);
        try
        {
            Marshal.StructureToPtr(info, ptr, false);
            if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, ptr, (uint)length))
            {
                int error = Marshal.GetLastWin32Error();
                CloseHandle(job);
                throw new Win32Exception(error, "SetInformationJobObject failed");
            }
        }
        finally
        {
            Marshal.FreeHGlobal(ptr);
        }
        return job;
    }

    public static ChildProcess StartSuspendedInJob(IntPtr job, string executable, string arguments, string workingDirectory)
    {
        var si = new STARTUPINFO();
        si.cb = (uint)Marshal.SizeOf(typeof(STARTUPINFO));
        PROCESS_INFORMATION pi;
        string commandLine = Quote(executable) + (String.IsNullOrWhiteSpace(arguments) ? "" : " " + arguments);
        var mutableCommandLine = new StringBuilder(commandLine);

        bool created = CreateProcess(
            executable,
            mutableCommandLine,
            IntPtr.Zero,
            IntPtr.Zero,
            true,
            CREATE_SUSPENDED,
            IntPtr.Zero,
            workingDirectory,
            ref si,
            out pi);

        if (!created)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "CreateProcess failed");

        try
        {
            if (!AssignProcessToJobObject(job, pi.hProcess))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "AssignProcessToJobObject failed");

            uint resume = ResumeThread(pi.hThread);
            if (resume == 0xFFFFFFFF)
                throw new Win32Exception(Marshal.GetLastWin32Error(), "ResumeThread failed");

            return new ChildProcess(pi.hProcess, unchecked((int)pi.dwProcessId));
        }
        catch
        {
            CloseHandle(pi.hProcess);
            throw;
        }
        finally
        {
            CloseHandle(pi.hThread);
        }
    }

    public static uint WaitForExit(ChildProcess child)
    {
        uint wait = WaitForSingleObject(child.ProcessHandle, INFINITE);
        if (wait != WAIT_OBJECT_0)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "WaitForSingleObject failed");
        uint exitCode;
        if (!GetExitCodeProcess(child.ProcessHandle, out exitCode))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "GetExitCodeProcess failed");
        return exitCode;
    }

    static string Quote(string value)
    {
        if (value.StartsWith("\"") && value.EndsWith("\"")) return value;
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }
}
'@
}

$JobName = ($StateName -replace '[^A-Za-z0-9_.-]', '-') + '-' + [guid]::NewGuid().ToString('N')
$JobHandle = [RdcKillJob]::CreateKillOnCloseJob($JobName)
$JobInfoPath = Join-Path $StateDir 'live.json'
$ExitReason = 'normal'

try {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host (' ' + $DisplayName.ToUpperInvariant() + ' ACCESS SWITCH') -ForegroundColor Cyan
    Write-Host ' ACCESS IS ENABLED ONLY WHILE THIS WINDOW IS OPEN' -ForegroundColor Yellow
    Write-Host ' Close this window or press Ctrl+C to disable access.' -ForegroundColor Yellow
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host ''

    $ConsecutiveFailures = 0
    while ($true) {
        if ($TestChildOnly) {
            $Executable = $env:ComSpec
            $Arguments = '/d /c "' + (Join-Path $Root 'tests\test-child.cmd') + '"'
        }
        else {
            $Executable = $TunnelClient
            if (-not (Test-Path $Executable)) { throw "Missing tunnel-client.exe: $Executable. Run Setup-All.cmd first." }
            $Arguments = 'run --profile ' + $Profile
        }

        $StartedAt = Get-Date
        $Child = [RdcKillJob]::StartSuspendedInJob($JobHandle, $Executable, $Arguments, $Root)
        $State = [ordered]@{
            supervisor_pid = $PID
            child_pid = $Child.ProcessId
            job_name = $JobName
            mode = $(if ($TestChildOnly) { 'test' } else { $StateName })
            profile = $Profile
            started_at = $StartedAt.ToString('o')
        }
        [IO.File]::WriteAllText($JobInfoPath, ($State | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
        Write-Host ("Started protected child PID {0}." -f $Child.ProcessId) -ForegroundColor Green

        $ExitCode = [RdcKillJob]::WaitForExit($Child)
        [RdcKillJob]::CloseHandle($Child.ProcessHandle) | Out-Null
        $Uptime = (Get-Date) - $StartedAt
        Write-Host ("Protected child exited code={0}, uptime={1:n1}s" -f $ExitCode, $Uptime.TotalSeconds) -ForegroundColor Yellow

        if ($TestChildOnly -and -not $TestRestart) { break }

        if ($Uptime.TotalSeconds -ge 30) { $ConsecutiveFailures = 0 }
        $ConsecutiveFailures++
        if ($ConsecutiveFailures -gt $MaxConsecutiveRestarts) {
            $ExitReason = 'restart-limit'
            throw "$DisplayName stopped after $MaxConsecutiveRestarts consecutive child failures. Access is now OFF."
        }
        Write-Host ("Restarting child in 2 seconds ({0}/{1})..." -f $ConsecutiveFailures, $MaxConsecutiveRestarts) -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}
catch {
    $ExitReason = 'error'
    Write-Host ''
    Write-Host ($DisplayName + ' supervisor error: ' + $_.Exception.Message) -ForegroundColor Red
    throw
}
finally {
    Remove-Item $JobInfoPath -Force -ErrorAction SilentlyContinue
    if ($JobHandle -ne [IntPtr]::Zero) {
        [RdcKillJob]::CloseHandle($JobHandle) | Out-Null
    }
    Write-Host ''
    Write-Host ($DisplayName.ToUpperInvariant() + ' ACCESS: OFF - protected process tree terminated.') -ForegroundColor Green
}
