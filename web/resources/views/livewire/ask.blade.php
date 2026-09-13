<div
    x-data="{
        queryId: @entangle('activeQueryId'),
        status: @js($activeQuery?->status),
        stage: @js($activeQuery?->current_stage),
        poller: null,
        stageLabel() {
            const labels = {
                plan_sql: 'Preparing query', guard_sql: 'Preparing query',
                run_sql: 'Querying database',
                plan_plot: 'Rendering chart', render: 'Rendering chart',
                summarize: 'Summarizing',
            };
            return labels[this.stage] ?? 'Working...';
        },
        start() {
            this.stop();
            this.poller = setInterval(() => this.poll(), 700);
        },
        stop() {
            if (this.poller) clearInterval(this.poller);
            this.poller = null;
        },
        poll() {
            fetch(`/ask/${this.queryId}/stream`)
                .then((r) => r.json())
                .then((data) => {
                    this.status = data.status;
                    this.stage = data.current_stage;
                    if (data.status === 'complete' || data.status === 'failed') {
                        this.stop();
                        $wire.call('refreshResult');
                    }
                });
        },
    }"
    x-init="if (queryId && status !== 'complete' && status !== 'failed') start()"
    x-on:query-started.window="status = 'pending'; stage = null; start()"
    class="flex flex-col lg:flex-row gap-6"
>
    {{-- Composer --}}
    <div class="lg:w-96 flex-shrink-0 space-y-4">
        <form wire:submit="submit" x-on:submit="$dispatch('query-started')" class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 space-y-3">
            <label class="field-label">Ask a question about excise data</label>
            <textarea wire:model="prompt" rows="4" placeholder="e.g. How did revenue trend across zones last financial year?"
                      class="field-input @error('prompt') field-error @enderror"></textarea>
            @error('prompt') <p class="field-err-msg">{{ $message }}</p> @enderror
            <button type="submit" wire:loading.attr="disabled" wire:target="submit"
                    class="w-full bg-govviolet-600 hover:bg-govviolet-700 disabled:opacity-50 text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center gap-2">
                <i class="ti ti-send"></i> Ask
            </button>
        </form>

        @if($activeQuery)
        <button wire:click="newQuestion" class="text-sm text-slate-500 hover:underline flex items-center gap-1.5">
            <i class="ti ti-plus"></i> New question
        </button>
        @endif
    </div>

    {{-- Canvas --}}
    <div class="flex-1 min-w-0 space-y-4">
        @if(!$activeQuery)
        <div class="stat-card justify-center text-center flex-col py-16">
            <div class="stat-icon bg-govviolet-100 dark:bg-govviolet-900/40 text-govviolet-600 mx-auto">
                <i class="ti ti-message-2-question"></i>
            </div>
            <p class="text-sm text-slate-400 dark:text-slate-500 mt-4">Ask a question to get started.</p>
        </div>
        @elseif($activeQuery->status === 'pending' || $activeQuery->status === 'running')
        <div class="stat-card justify-center text-center flex-col py-16">
            <i class="ti ti-loader-2 animate-spin text-govviolet-600 text-2xl"></i>
            <p class="text-sm text-slate-500 dark:text-slate-400 mt-4" x-text="stageLabel()">Working...</p>
        </div>
        @elseif($activeQuery->status === 'failed')
        <div class="flex items-start gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg px-4 py-3">
            <i class="ti ti-alert-circle flex-shrink-0 mt-0.5"></i>
            <span>{{ $activeQuery->error_message ?? 'The query failed. Please try again.' }}</span>
        </div>
        @else
            @if($activeQuery->chartArtifact?->spec)
            <div class="stat-card block" wire:key="chart-{{ $activeQuery->id }}" wire:ignore.self>
                <div x-init="Plotly.newPlot($el, @js($activeQuery->chartArtifact->spec['data'] ?? []), @js($activeQuery->chartArtifact->spec['layout'] ?? []), {responsive: true})" style="width:100%;min-height:360px;"></div>
            </div>
            @endif

            @if($activeQuery->summary)
            <div class="stat-card block">
                <p class="text-sm text-slate-700 dark:text-slate-200">{{ $activeQuery->summary }}</p>
            </div>
            @endif

            @if($activeQuery->rows_preview)
            <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                <div class="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700">
                    <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">{{ $activeQuery->row_count }} rows</p>
                    <div class="flex items-center gap-3 text-xs">
                        <a href="{{ route('ask.export', ['query' => $activeQuery->id, 'format' => 'csv']) }}" class="text-govviolet-600 hover:underline">CSV</a>
                        <a href="{{ route('ask.export', ['query' => $activeQuery->id, 'format' => 'xlsx']) }}" class="text-govviolet-600 hover:underline">XLSX</a>
                    </div>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-sm">
                        <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                            <tr>
                                @foreach(array_keys($activeQuery->rows_preview[0] ?? []) as $column)
                                <th class="px-4 py-2">{{ $column }}</th>
                                @endforeach
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                            @foreach($activeQuery->rows_preview as $row)
                            <tr>
                                @foreach($row as $value)
                                <td class="px-4 py-2 text-slate-600 dark:text-slate-300">{{ $value }}</td>
                                @endforeach
                            </tr>
                            @endforeach
                        </tbody>
                    </table>
                </div>
            </div>
            @endif

            @if($activeQuery->sql)
            <div x-data="{ open: false, copied: false }" class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                <button x-on:click="open = !open" class="w-full flex items-center justify-between px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <span>Generated SQL</span>
                    <i class="ti" :class="open ? 'ti-chevron-up' : 'ti-chevron-down'"></i>
                </button>
                <div x-show="open" x-cloak class="px-4 pb-4">
                    <pre class="text-xs bg-slate-50 dark:bg-slate-900 rounded-lg p-3 overflow-x-auto">{{ $activeQuery->sql }}</pre>
                    <button
                        x-on:click="navigator.clipboard.writeText(@js($activeQuery->sql)); copied = true; setTimeout(() => copied = false, 1500)"
                        class="mt-2 text-xs text-govviolet-600 hover:underline flex items-center gap-1">
                        <i class="ti" :class="copied ? 'ti-check' : 'ti-copy'"></i>
                        <span x-text="copied ? 'Copied' : 'Copy'"></span>
                    </button>
                </div>
            </div>
            @endif
        @endif
    </div>
</div>

@push('scripts')
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2/plotly.min.js"></script>
@endpush
