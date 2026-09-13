<div wire:poll.15s class="space-y-5">
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="stat-card">
            <div class="stat-icon {{ $orchestratorHealth ? 'bg-green-100 dark:bg-green-900/40 text-green-600' : 'bg-red-100 dark:bg-red-900/40 text-red-600' }}">
                <i class="ti ti-cpu"></i>
            </div>
            <div>
                <p class="text-xs text-slate-400 uppercase tracking-wide">Orchestrator</p>
                <p class="text-lg font-semibold">{{ $orchestratorHealth ? 'Reachable' : 'Unreachable' }}</p>
                @if($orchestratorHealth)
                <p class="text-xs text-slate-400">Postgres: {{ $orchestratorHealth['postgres'] ?? '?' }} &middot; {{ $orchestratorHealth['kb_docs'] ?? 0 }} KB docs</p>
                @endif
            </div>
        </div>

        <div class="stat-card">
            <div class="stat-icon {{ $failedJobs > 0 ? 'bg-red-100 dark:bg-red-900/40 text-red-600' : 'bg-govviolet-100 dark:bg-govviolet-900/40 text-govviolet-600' }}">
                <i class="ti ti-list-check"></i>
            </div>
            <div>
                <p class="text-xs text-slate-400 uppercase tracking-wide">Queue</p>
                <p class="text-lg font-semibold">{{ $pendingJobs }} pending</p>
                <p class="text-xs text-slate-400">{{ $failedJobs }} failed</p>
            </div>
        </div>

        <div class="stat-card">
            <div class="stat-icon bg-govsaffron-100 dark:bg-govsaffron-900/40 text-govsaffron-600">
                <i class="ti ti-gauge"></i>
            </div>
            <div>
                <p class="text-xs text-slate-400 uppercase tracking-wide">Load average</p>
                <p class="text-lg font-semibold">{{ $vitals['load'] ? implode(' / ', array_map(fn($l) => number_format($l, 2), $vitals['load'])) : 'n/a' }}</p>
                <p class="text-xs text-slate-400">{{ $vitals['cpu_cores'] ?? '?' }} cores @if($vitals['cpu_temp_c']) &middot; {{ number_format($vitals['cpu_temp_c'], 0) }}&deg;C @endif</p>
            </div>
        </div>

        <div class="stat-card">
            <div class="stat-icon bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
                <i class="ti ti-server-2"></i>
            </div>
            <div>
                <p class="text-xs text-slate-400 uppercase tracking-wide">Memory available</p>
                <p class="text-lg font-semibold">
                    @if($vitals['mem_available_mb'] && $vitals['mem_total_mb'])
                        {{ number_format($vitals['mem_available_mb'] / 1024, 1) }} / {{ number_format($vitals['mem_total_mb'] / 1024, 1) }} GB
                    @else
                        n/a
                    @endif
                </p>
                <p class="text-xs text-slate-400">{{ $logSignals['errors_last_hour'] }} error(s) in the last hour</p>
            </div>
        </div>
    </div>

    <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div class="px-4 py-3 border-b border-slate-100 dark:border-slate-700">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">AI usage — Ask (one-shot queries)</p>
        </div>
        <div class="overflow-x-auto">
            <table class="w-full text-sm">
                <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    <tr>
                        <th class="px-4 py-2">Model</th>
                        <th class="px-4 py-2">Queries</th>
                        <th class="px-4 py-2">Prompt tokens</th>
                        <th class="px-4 py-2">Completion tokens</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                    @forelse($usageByModel as $row)
                    <tr>
                        <td class="px-4 py-2 font-medium">{{ $row->model }}</td>
                        <td class="px-4 py-2">{{ $row->queries }}</td>
                        <td class="px-4 py-2">{{ number_format($row->prompt_tokens) }}</td>
                        <td class="px-4 py-2">{{ number_format($row->completion_tokens) }}</td>
                    </tr>
                    @empty
                    <tr><td colspan="4" class="px-4 py-6 text-center text-slate-400">No queries yet.</td></tr>
                    @endforelse
                </tbody>
            </table>
        </div>
    </div>

    <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div class="px-4 py-3 border-b border-slate-100 dark:border-slate-700">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">AI usage — Chat</p>
        </div>
        <div class="overflow-x-auto">
            <table class="w-full text-sm">
                <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    <tr>
                        <th class="px-4 py-2">Model</th>
                        <th class="px-4 py-2">Assistant messages</th>
                        <th class="px-4 py-2">Prompt tokens</th>
                        <th class="px-4 py-2">Completion tokens</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                    @forelse($chatUsageByModel as $row)
                    <tr>
                        <td class="px-4 py-2 font-medium">{{ $row->model }}</td>
                        <td class="px-4 py-2">{{ $row->messages }}</td>
                        <td class="px-4 py-2">{{ number_format($row->prompt_tokens) }}</td>
                        <td class="px-4 py-2">{{ number_format($row->completion_tokens) }}</td>
                    </tr>
                    @empty
                    <tr><td colspan="4" class="px-4 py-6 text-center text-slate-400">No chat messages yet.</td></tr>
                    @endforelse
                </tbody>
            </table>
        </div>
    </div>

    <div class="stat-card">
        <div class="stat-icon bg-govviolet-100 dark:bg-govviolet-900/40 text-govviolet-600">
            <i class="ti ti-thumb-up"></i>
        </div>
        <div>
            <p class="text-xs text-slate-400 uppercase tracking-wide">Ask feedback</p>
            <p class="text-lg font-semibold">{{ $feedbackUp }} up &middot; {{ $feedbackDown }} down</p>
        </div>
    </div>
</div>
