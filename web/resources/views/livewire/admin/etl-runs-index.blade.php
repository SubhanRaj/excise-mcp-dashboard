<div>
    @if($unavailable)
    <div class="flex items-start gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg px-4 py-3 mb-5">
        <i class="ti ti-alert-circle flex-shrink-0 mt-0.5"></i>
        <span>The orchestrator is unreachable, or `excise_ro` hasn't been granted read access to schema `etl` yet (`OPERATOR_SETUP.md` §Data bank) — ingestion runs can't be listed right now.</span>
    </div>
    @endif

    <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden overflow-x-auto">
        <table class="w-full text-sm">
            <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <tr>
                    <th class="px-4 py-3">Started</th>
                    <th class="px-4 py-3">Source</th>
                    <th class="px-4 py-3">Period</th>
                    <th class="px-4 py-3">Status</th>
                    <th class="px-4 py-3">Seen</th>
                    <th class="px-4 py-3">Upserted</th>
                    <th class="px-4 py-3">Quarantined</th>
                    <th class="px-4 py-3"></th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                @forelse($runs as $run)
                <tr wire:key="run-{{ $run['id'] }}">
                    <td class="px-4 py-3 text-slate-500 dark:text-slate-400 whitespace-nowrap">{{ \Illuminate\Support\Carbon::parse($run['started_at'])->ist()->format('d M Y, h:i A') }}</td>
                    <td class="px-4 py-3 text-slate-700 dark:text-slate-200">
                        {{ $run['source'] }}
                        <span class="block text-xs text-slate-400">{{ $run['source_ref'] }}</span>
                    </td>
                    <td class="px-4 py-3 text-slate-500 dark:text-slate-400">{{ $run['report_period'] ?? '—' }}</td>
                    <td class="px-4 py-3">
                        <span class="badge {{ match($run['status']) {
                            'ok' => 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
                            'failed' => 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
                            'partial' => 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
                            default => 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
                        } }}">{{ ucfirst($run['status']) }}</span>
                        @if($run['error'])
                        <span class="block text-xs text-red-500 mt-0.5">{{ Str::limit($run['error'], 80) }}</span>
                        @endif
                    </td>
                    <td class="px-4 py-3 text-slate-500 dark:text-slate-400">{{ $run['rows_seen'] }}</td>
                    <td class="px-4 py-3 text-slate-500 dark:text-slate-400">{{ $run['rows_upserted'] }}</td>
                    <td class="px-4 py-3 text-slate-500 dark:text-slate-400">{{ $run['rows_quarantined'] }}</td>
                    <td class="px-4 py-3">
                        @if($run['rows_quarantined'] > 0)
                        <button type="button" wire:click="viewQuarantine({{ $run['id'] }})" class="text-govviolet-600 hover:underline text-xs">
                            {{ $selectedRunId === $run['id'] ? 'Hide' : 'View' }} reasons
                        </button>
                        @endif
                    </td>
                </tr>
                @if($selectedRunId === $run['id'])
                <tr>
                    <td colspan="8" class="px-4 py-3 bg-slate-50 dark:bg-slate-900/40">
                        @forelse($quarantine as $row)
                        <div class="text-xs text-slate-600 dark:text-slate-300 py-1 border-b border-slate-100 dark:border-slate-700 last:border-0">
                            <span class="font-medium">{{ $row['reason'] }}</span>
                            <span class="block font-mono text-slate-400 mt-0.5">{{ json_encode($row['raw_row']) }}</span>
                        </div>
                        @empty
                        <p class="text-xs text-slate-400">No quarantined rows for this run.</p>
                        @endforelse
                    </td>
                </tr>
                @endif
                @empty
                <tr><td colspan="8" class="px-4 py-8 text-center text-slate-400">No ingestion runs recorded yet.</td></tr>
                @endforelse
            </tbody>
        </table>
    </div>

    @if($total > $perPage)
    <div class="flex items-center justify-between mt-4 text-sm">
        <button type="button" wire:click="previousPage" @if($page <= 1) disabled @endif class="text-govviolet-600 hover:underline disabled:text-slate-300 disabled:no-underline">Previous</button>
        <span class="text-slate-400 text-xs">Page {{ $page }} of {{ (int) ceil($total / $perPage) }}</span>
        <button type="button" wire:click="nextPage" @if($page >= ceil($total / $perPage)) disabled @endif class="text-govviolet-600 hover:underline disabled:text-slate-300 disabled:no-underline">Next</button>
    </div>
    @endif
</div>
