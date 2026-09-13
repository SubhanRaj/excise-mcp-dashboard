<?php

namespace App\Livewire\Admin;

use App\Models\Message;
use App\Models\Query;
use App\Models\QueryFeedback;
use App\Services\OrchestratorClient;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;
use Livewire\Component;

/**
 * A super-admin overview of the running system: queue/orchestrator health, box
 * vitals, and how the AI is actually being used (models, tokens, feedback).
 * Livewire-native (this app's own convention), not the plain-controller +
 * Alpine-polling pattern pdf-markdown-pipeline's equivalent screen uses —
 * wire:poll covers the same "refresh every few seconds" need without a
 * second, hand-rolled JSON endpoint.
 */
class SystemHealth extends Component
{
    public function mount(): void
    {
        abort_unless(auth()->user()->hasPrivilege('system.monitor'), 403);
    }

    /**
     * Direct /proc and sys_getloadavg() reads, exactly like
     * pdf-markdown-pipeline's DocumentController::serverVitals() — every read
     * is wrapped so a missing file (a container, a different kernel) degrades
     * to null instead of a 500.
     *
     * @return array{load: array<int, float>|null, cpu_cores: int|null, mem_total_mb: int|null, mem_available_mb: int|null, cpu_temp_c: float|null}
     */
    private function serverVitals(): array
    {
        $load = sys_getloadavg();

        $cpuCores = null;
        try {
            $nproc = trim((string) shell_exec('nproc'));
            $cpuCores = $nproc !== '' ? (int) $nproc : null;
        } catch (\Throwable) {
            // stays null
        }

        $memTotal = null;
        $memAvailable = null;
        try {
            $meminfo = File::get('/proc/meminfo');
            if (preg_match('/MemTotal:\s+(\d+)/', $meminfo, $m)) {
                $memTotal = (int) round(((int) $m[1]) / 1024);
            }
            if (preg_match('/MemAvailable:\s+(\d+)/', $meminfo, $m)) {
                $memAvailable = (int) round(((int) $m[1]) / 1024);
            }
        } catch (\Throwable) {
            // stays null
        }

        $cpuTemp = null;
        try {
            $readings = [];
            foreach (glob('/sys/class/thermal/thermal_zone*/temp') ?: [] as $path) {
                $raw = trim((string) File::get($path));
                if ($raw !== '') {
                    $readings[] = ((int) $raw) / 1000;
                }
            }
            $cpuTemp = $readings === [] ? null : max($readings);
        } catch (\Throwable) {
            // stays null
        }

        return [
            'load' => $load === false ? null : $load,
            'cpu_cores' => $cpuCores,
            'mem_total_mb' => $memTotal,
            'mem_available_mb' => $memAvailable,
            'cpu_temp_c' => $cpuTemp,
        ];
    }

    /**
     * Error/slow-query line counts from the last hour of laravel.log, the
     * same log-tail approach pdf-markdown-pipeline uses in place of Pulse's
     * Exceptions/SlowQueries cards.
     *
     * @return array{errors_last_hour: int}
     */
    private function logSignals(): array
    {
        $path = storage_path('logs/laravel.log');
        if (! is_file($path)) {
            return ['errors_last_hour' => 0];
        }

        $size = filesize($path) ?: 0;
        $handle = fopen($path, 'r');
        if ($handle === false) {
            return ['errors_last_hour' => 0];
        }
        fseek($handle, -1 * min($size, 2 * 1024 * 1024), SEEK_END);
        $tail = stream_get_contents($handle) ?: '';
        fclose($handle);

        $cutoff = now()->subHour()->format('Y-m-d H:');
        $errors = 0;
        foreach (explode("\n", $tail) as $line) {
            if (str_contains($line, '.ERROR') && str_starts_with($line, '[')
                && str_starts_with(substr($line, 1), $cutoff)) {
                $errors++;
            }
        }

        return ['errors_last_hour' => $errors];
    }

    public function render()
    {
        $orchestratorHealth = null;
        try {
            $orchestratorHealth = app(OrchestratorClient::class)->health();
        } catch (\Throwable) {
            // stays null — the view shows "unreachable"
        }

        $usageByModel = Query::query()
            ->selectRaw('model, count(*) as queries, sum(prompt_tokens) as prompt_tokens, sum(completion_tokens) as completion_tokens')
            ->whereNotNull('model')
            ->groupBy('model')
            ->get();

        $chatUsageByModel = Message::query()
            ->where('role', 'assistant')
            ->selectRaw('model, count(*) as messages, sum(prompt_tokens) as prompt_tokens, sum(completion_tokens) as completion_tokens')
            ->whereNotNull('model')
            ->groupBy('model')
            ->get();

        return view('livewire.admin.system-health', [
            'orchestratorHealth' => $orchestratorHealth,
            'pendingJobs' => DB::table('jobs')->count(),
            'failedJobs' => DB::table('failed_jobs')->count(),
            'lastAiActivity' => Query::max('updated_at') ?? Message::max('updated_at'),
            'vitals' => $this->serverVitals(),
            'logSignals' => $this->logSignals(),
            'usageByModel' => $usageByModel,
            'chatUsageByModel' => $chatUsageByModel,
            'feedbackUp' => QueryFeedback::where('thumbs_up', true)->count(),
            'feedbackDown' => QueryFeedback::where('thumbs_up', false)->count(),
        ])->layout('components.layout', ['pageTitle' => 'System health', 'title' => 'System health']);
    }
}
