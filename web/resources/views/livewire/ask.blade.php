<div
    x-data="{
        queryId: @entangle('activeQueryId'),
        status: @js($activeQuery?->status),
        stage: @js($activeQuery?->current_stage),
        // Every distinct stage seen so far, oldest first — rendered as a growing checklist
        // (ti-check for everything but the last entry, a spinner on the last) instead of one
        // line of text overwriting itself, so a run that takes a while shows forward progress
        // rather than looking stuck on a single spinner (plan_sql -> guard_sql -> run_sql ->
        // plan_plot -> render, skipped for a single-row result -> summarize, pipeline.py).
        stageLog: @js($activeQuery?->current_stage ? [$activeQuery->current_stage] : []),
        stageLabels: {
            plan_sql: 'Planning the query', guard_sql: 'Validating the query',
            run_sql: 'Querying the database',
            plan_plot: 'Planning the chart', render: 'Rendering the chart',
            summarize: 'Summarizing the result',
        },
        stageLabel(name) {
            return this.stageLabels[name] ?? name;
        },
        poller: null,
        start() {
            this.stop();
            this.poller = setInterval(() => this.poll(), 700);
        },
        stop() {
            if (this.poller) clearInterval(this.poller);
            this.poller = null;
        },
        // wire:navigate swaps the page body without a real reload, which never fires this
        // Alpine component's own teardown unless it's wired to destroy() — without it, the
        // poller kept fetching /ask/{id}/stream forever from whatever page was navigated to
        // next, same class of leak chatThread() already guards against in chat.blade.php.
        destroy() {
            this.stop();
        },
        poll() {
            fetch(`/ask/${this.queryId}/stream`)
                .then((r) => r.json())
                .then((data) => {
                    this.status = data.status;
                    this.stage = data.current_stage;
                    if (this.stage && this.stageLog[this.stageLog.length - 1] !== this.stage) {
                        this.stageLog.push(this.stage);
                    }
                    if (data.status === 'complete' || data.status === 'failed') {
                        this.stop();
                        $wire.call('refreshResult');
                    }
                });
        },
    }"
    x-init="if (queryId && status !== 'complete' && status !== 'failed') start()"
    x-on:query-started.window="status = 'pending'; stage = null; stageLog = []; start()"
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
        {{-- Plain navigation, not wire:navigate — matching Chat's own rail: a fresh page
             load always re-mounts from the database, so a previously-finished query never
             shows a stage spinner left over from before it completed. --}}
        <a href="{{ route('ask') }}" class="text-sm text-slate-500 hover:underline flex items-center gap-1.5">
            <i class="ti ti-plus"></i> New question
        </a>
        @endif

        @if($recentQueries->isNotEmpty())
        <div class="space-y-1">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-400 px-1">Recent questions</p>
            <div class="max-h-96 overflow-y-auto space-y-1">
                @foreach($recentQueries as $q)
                <div class="group relative flex items-center" x-data="{ menuOpen: false }">
                    <a href="{{ route('ask.show', $q) }}"
                       class="flex-1 min-w-0 block pl-3 pr-8 py-2 rounded-lg text-sm truncate {{ $activeQuery?->id === $q->id ? 'bg-govviolet-50 dark:bg-govviolet-900/30 text-govviolet-700 dark:text-govviolet-300 font-medium' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800' }}">
                        {{ $q->prompt }}
                    </a>
                    <button x-on:click="menuOpen = !menuOpen"
                            class="absolute right-1.5 w-7 h-7 flex items-center justify-center rounded text-slate-400 opacity-60 group-hover:opacity-100 focus-visible:opacity-100 hover:bg-slate-200 dark:hover:bg-slate-700"
                            title="Question options">
                        <i class="ti ti-dots-vertical text-base"></i>
                    </button>
                    <div x-show="menuOpen" x-cloak x-on:click.outside="menuOpen = false"
                         class="absolute right-0 top-full z-10 mt-1 w-44 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg py-1 text-xs">
                        <button wire:click="deleteQuery('{{ $q->id }}')" x-on:click="menuOpen = false"
                                class="w-full text-left px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300">
                            Delete
                        </button>
                        <button wire:click="forceDeleteQuery('{{ $q->id }}')"
                                wire:confirm="Permanently delete this question? This cannot be undone."
                                x-on:click="menuOpen = false"
                                class="w-full text-left px-3 py-1.5 hover:bg-red-50 dark:hover:bg-red-900/30 text-red-600">
                            Delete permanently
                        </button>
                    </div>
                </div>
                @endforeach
            </div>
        </div>
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
        <div class="stat-card justify-center flex-col py-12">
            <template x-if="stageLog.length === 0">
                <div class="flex flex-col items-center text-center">
                    <i class="ti ti-loader-2 animate-spin text-govviolet-600 text-2xl"></i>
                    <p class="text-sm text-slate-500 dark:text-slate-400 mt-4">Starting...</p>
                </div>
            </template>
            <ul class="space-y-2.5 w-full max-w-xs mx-auto" x-show="stageLog.length > 0">
                <template x-for="(name, i) in stageLog" :key="name">
                    <li class="flex items-center gap-2.5 text-sm"
                        :class="i === stageLog.length - 1 ? 'text-slate-700 dark:text-slate-200 font-medium' : 'text-slate-400 dark:text-slate-500'">
                        <i class="ti flex-shrink-0" :class="i === stageLog.length - 1 ? 'ti-loader-2 animate-spin text-govviolet-600' : 'ti-check text-green-600'"></i>
                        <span x-text="stageLabel(name)"></span>
                    </li>
                </template>
            </ul>
        </div>
        @elseif($activeQuery->status === 'failed')
        <div class="flex items-start gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg px-4 py-3">
            <i class="ti ti-alert-circle flex-shrink-0 mt-0.5"></i>
            <div>
                <span>{{ $activeQuery->error_message ?: 'The query failed. Please try again.' }}</span>
                @if(config('app.debug'))
                <p class="text-xs text-red-600/70 dark:text-red-400/70 mt-1 font-mono">
                    stage: {{ $activeQuery->current_stage ?? 'unknown' }}
                    @if($activeQuery->request_id) &middot; request_id: {{ $activeQuery->request_id }} @endif
                </p>
                @endif
            </div>
        </div>
        @else
            @if($activeQuery->chartArtifact?->spec)
            <div class="stat-card block" wire:key="chart-{{ $activeQuery->id }}" wire:ignore.self>
                <div class="flex justify-end gap-3 text-xs mb-1">
                    @foreach(['png', 'svg', 'pdf'] as $format)
                    <a href="{{ route('chart-artifacts.export', ['chartArtifact' => $activeQuery->chartArtifact->id, 'format' => $format]) }}" class="text-govviolet-600 hover:underline uppercase">{{ $format }}</a>
                    @endforeach
                </div>
                <div x-init="Plotly.newPlot($el, @js($activeQuery->chartArtifact->spec['data'] ?? []), @js($activeQuery->chartArtifact->spec['layout'] ?? []), {responsive: true})" style="width:100%;min-height:360px;"></div>
            </div>
            @endif

            @if($activeQuery->summary)
            <div class="stat-card block" x-data="{ copied: false }">
                <p class="text-sm text-slate-700 dark:text-slate-200">{{ $activeQuery->summary }}</p>
                <button x-on:click="navigator.clipboard.writeText(@js($activeQuery->summary)); copied = true; setTimeout(() => copied = false, 1500)"
                        class="mt-2 text-xs text-govviolet-600 hover:underline flex items-center gap-1">
                    <i class="ti" :class="copied ? 'ti-check' : 'ti-copy'"></i>
                    <span x-text="copied ? 'Copied' : 'Copy'"></span>
                </button>
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

            @if($activeQuery->status === 'complete')
            <div class="flex flex-wrap items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
                <span>Was this useful?</span>
                <button wire:click="giveFeedback(true)"
                        class="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 {{ $activeQuery->feedback->first()?->thumbs_up === true ? 'text-green-600' : '' }}"
                        title="Yes">
                    <i class="ti ti-thumb-up"></i>
                </button>
                <button wire:click="giveFeedback(false)"
                        class="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 {{ $activeQuery->feedback->first()?->thumbs_up === false ? 'text-red-600' : '' }}"
                        title="No">
                    <i class="ti ti-thumb-down"></i>
                </button>
                <input type="text" wire:model="feedbackNote" placeholder="Add a note (optional)"
                       class="field-input !py-1.5 text-xs flex-1 min-w-[10rem] max-w-xs">
                @if($activeQuery->feedback->first()?->note)
                <span class="text-xs italic">Saved: "{{ $activeQuery->feedback->first()->note }}"</span>
                @endif
            </div>
            @endif
        @endif
    </div>
</div>

@push('scripts')
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2/plotly.min.js"></script>
@endpush
