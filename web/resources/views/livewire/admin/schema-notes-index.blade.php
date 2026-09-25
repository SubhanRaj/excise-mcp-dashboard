<div class="space-y-4">
    <p class="text-sm text-slate-500 dark:text-slate-400">
        Every table the chat and Ask models can query, and what each one means — a note
        here rides straight into the prompt those models see, the same way as the
        built-in schema notes.
    </p>

    @if($unavailable)
    <div class="flex items-start gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg px-4 py-3">
        <i class="ti ti-alert-circle flex-shrink-0 mt-0.5"></i>
        <span>The orchestrator is unreachable — the schema can't be listed right now.</span>
    </div>
    @endif

    @foreach($tables as $table)
    <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5" wire:key="table-{{ $table['name'] }}">
        <div class="flex items-center justify-between mb-3">
            <div>
                <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-100">{{ $table['display_name'] }}</h3>
                <p class="font-mono text-xs text-slate-400 dark:text-slate-500 mt-0.5">analytics.{{ $table['name'] }}</p>
                @if($table['summary'] ?? null)
                <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">{{ $table['summary'] }}</p>
                @endif
                @if($table['note'] ?? null)
                <details class="mt-1">
                    <summary class="text-xs text-govviolet-600 cursor-pointer hover:underline">Technical note (what the AI is told)</summary>
                    <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">{{ $table['note'] }}</p>
                </details>
                @endif
            </div>
            <button type="button" wire:click="toggleSample('{{ $table['name'] }}')" class="text-govviolet-600 hover:underline text-xs flex-shrink-0 ml-3">
                {{ $expandedTable === $table['name'] ? 'Hide columns & sample data' : count($table['columns']).' columns — show columns & sample data' }}
            </button>
        </div>

        @if($expandedTable === $table['name'])
        <div class="mb-4 overflow-x-auto border border-slate-100 dark:border-slate-700 rounded-lg">
            <table class="w-full text-xs">
                @if(count($sample))
                <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-slate-500 dark:text-slate-400">
                    <tr>
                        @foreach(array_keys($sample[0]) as $column)
                        <th class="px-3 py-2 whitespace-nowrap">{{ $column }}</th>
                        @endforeach
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                    @foreach($sample as $row)
                    <tr>
                        @foreach($row as $value)
                        <td class="px-3 py-2 text-slate-600 dark:text-slate-300 whitespace-nowrap">{{ $value ?? '—' }}</td>
                        @endforeach
                    </tr>
                    @endforeach
                </tbody>
                @else
                <tbody><tr><td class="px-3 py-4 text-center text-slate-400">No rows.</td></tr></tbody>
                @endif
            </table>
        </div>
        @endif

        <form wire:submit="saveTable('{{ $table['name'] }}')" class="space-y-3">
            <div>
                <label class="field-label">What is this table for?</label>
                <textarea wire:model="notes.{{ $table['name'] }}.__table__" rows="2" class="field-input" placeholder="{{ $table['note'] ?? 'e.g. one row per wholesale-to-retail transport pass...' }}"></textarea>
            </div>

            @if($expandedTable === $table['name'])
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                @foreach($table['columns'] as $column)
                <div>
                    <label class="field-label font-mono">{{ $column['name'] }} <span class="text-slate-400 font-normal">{{ $column['data_type'] }}</span></label>
                    <input type="text" wire:model="notes.{{ $table['name'] }}.{{ $column['name'] }}" class="field-input" placeholder="{{ $column['note'] ?? 'What does this column mean?' }}">
                </div>
                @endforeach
            </div>
            @endif

            <button type="submit" class="bg-govviolet-600 hover:bg-govviolet-700 text-white text-sm font-semibold py-2 px-4 rounded-lg transition-colors">
                Save notes
            </button>
        </form>
    </div>
    @endforeach
</div>
