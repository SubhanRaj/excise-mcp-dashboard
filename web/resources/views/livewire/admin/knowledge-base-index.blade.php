<div class="space-y-8">
    <section class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
        <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-4">Upload a document</h2>
        <form wire:submit="upload" class="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-4 items-start">
            <div class="space-y-3">
                <div>
                    <label class="field-label">Title</label>
                    <input type="text" wire:model="title" class="field-input @error('title') field-error @enderror">
                    @error('title') <p class="field-err-msg">{{ $message }}</p> @enderror
                </div>
                <div>
                    <label class="field-label">Markdown file (.md, max 2 MB)</label>
                    <input type="file" wire:model="file" accept=".md" class="field-input @error('file') field-error @enderror">
                    @error('file') <p class="field-err-msg">{{ $message }}</p> @enderror
                    <div wire:loading wire:target="file" class="text-xs text-slate-400 mt-1">Uploading...</div>
                </div>
            </div>
            <button type="submit" class="bg-govviolet-600 hover:bg-govviolet-700 text-white text-sm font-semibold py-2.5 px-5 rounded-lg transition-colors self-end">
                <i class="ti ti-upload"></i> Upload
            </button>
        </form>
    </section>

    <section>
        <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-4">Pending uploads</h2>
        <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
            <table class="w-full text-sm">
                <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    <tr>
                        <th class="px-4 py-3">Title</th>
                        <th class="px-4 py-3">Uploaded by</th>
                        <th class="px-4 py-3">Status</th>
                        <th class="px-4 py-3 text-right">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                    @forelse($uploads as $upload)
                    <tr>
                        <td class="px-4 py-3 text-slate-800 dark:text-slate-100">{{ $upload->title }}</td>
                        <td class="px-4 py-3 text-slate-600 dark:text-slate-300">{{ $upload->uploader->name }}</td>
                        <td class="px-4 py-3">
                            <span class="badge {{ $upload->status === 'withdrawn' ? 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400' }}">
                                {{ ucfirst($upload->status) }}
                            </span>
                        </td>
                        <td class="px-4 py-3 text-right">
                            @if($upload->status !== 'withdrawn')
                            <button wire:click="withdraw('{{ $upload->id }}')" wire:confirm="Withdraw \"{{ $upload->title }}\"?"
                                    class="text-slate-400 hover:text-red-600 p-1.5" title="Withdraw">
                                <i class="ti ti-file-off"></i>
                            </button>
                            @endif
                        </td>
                    </tr>
                    @empty
                    <tr><td colspan="4" class="px-4 py-8 text-center text-slate-400">No uploads yet.</td></tr>
                    @endforelse
                </tbody>
            </table>
        </div>
        <div class="mt-4">{{ $uploads->links() }}</div>
    </section>

    <section>
        <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-4">Ingested corpus</h2>

        <form wire:submit="searchCorpus" class="flex gap-2 mb-4">
            <input type="text" wire:model="corpusSearch" placeholder="Search the corpus..." class="field-input">
            <button type="submit" class="bg-slate-700 hover:bg-slate-800 text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors">
                <i class="ti ti-search"></i>
            </button>
        </form>

        @if($corpusUnavailable)
        <div class="flex items-center gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg px-4 py-3">
            <i class="ti ti-alert-circle"></i> The orchestrator is unreachable — the corpus can't be browsed right now.
        </div>
        @else
            @php $rows = $corpusResults ?? ($corpus['documents'] ?? []); @endphp
            <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                <table class="w-full text-sm">
                    <thead class="bg-slate-50 dark:bg-slate-900/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        <tr>
                            <th class="px-4 py-3">Title</th>
                            <th class="px-4 py-3">Type</th>
                            <th class="px-4 py-3">Status</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
                        @forelse($rows as $doc)
                        <tr>
                            <td class="px-4 py-3">
                                @if(!empty($doc['source_url']))
                                <a href="{{ $doc['source_url'] }}" target="_blank" rel="noopener" class="text-govviolet-600 hover:underline">{{ $doc['title'] }}</a>
                                @else
                                <span class="text-slate-800 dark:text-slate-100">{{ $doc['title'] }}</span>
                                @endif
                            </td>
                            <td class="px-4 py-3 text-slate-600 dark:text-slate-300">{{ $doc['doc_type'] ?? '—' }}</td>
                            <td class="px-4 py-3">
                                @if(!empty($doc['withdrawn_at']))
                                <span class="badge bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">Withdrawn</span>
                                @else
                                <span class="badge bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">Active</span>
                                @endif
                            </td>
                        </tr>
                        @empty
                        <tr><td colspan="3" class="px-4 py-8 text-center text-slate-400">No documents found.</td></tr>
                        @endforelse
                    </tbody>
                </table>
            </div>
        @endif
    </section>
</div>
