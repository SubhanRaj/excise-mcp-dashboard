<div>
    <div class="flex items-center justify-between mb-5">
        <p class="text-sm text-slate-500 dark:text-slate-400">Google Drive, Sheets, and Docs sources for ETL ingestion.</p>
        <a href="{{ route('google.connect') }}"
           class="inline-flex items-center gap-2 bg-govviolet-600 hover:bg-govviolet-700 text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors">
            <i class="ti ti-brand-google"></i> Connect Google account
        </a>
    </div>

    <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
        <table class="w-full text-sm">
            <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <tr>
                    <th class="px-4 py-3">Account</th>
                    <th class="px-4 py-3">Connected by</th>
                    <th class="px-4 py-3">Status</th>
                    <th class="px-4 py-3 text-right">Actions</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                @forelse($connections as $connection)
                <tr>
                    <td class="px-4 py-3 text-slate-800 dark:text-slate-100">{{ $connection->email }}</td>
                    <td class="px-4 py-3 text-slate-600 dark:text-slate-300">{{ $connection->user->name }}</td>
                    <td class="px-4 py-3">
                        @if($connection->needsReconnect())
                        <span class="badge bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">Reconnect needed</span>
                        @else
                        <span class="badge bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">Connected</span>
                        @endif
                    </td>
                    <td class="px-4 py-3 text-right">
                        <button wire:click="disconnect('{{ $connection->id }}')" wire:confirm="Disconnect {{ $connection->email }}?"
                                class="text-slate-400 hover:text-red-600 p-1.5" title="Disconnect">
                            <i class="ti ti-plug-connected-x"></i>
                        </button>
                    </td>
                </tr>
                @empty
                <tr><td colspan="4" class="px-4 py-8 text-center text-slate-400">No Google accounts connected yet.</td></tr>
                @endforelse
            </tbody>
        </table>
    </div>
</div>
