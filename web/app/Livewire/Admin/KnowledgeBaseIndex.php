<?php

namespace App\Livewire\Admin;

use App\Livewire\Concerns\ConfirmsWithSweetAlert;
use App\Models\KbUpload;
use App\Services\OrchestratorClient;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Pagination\LengthAwarePaginator;
use Illuminate\Pagination\Paginator;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use Livewire\Attributes\Validate;
use Livewire\Component;
use Livewire\WithFileUploads;
use Livewire\WithPagination;

class KnowledgeBaseIndex extends Component
{
    use ConfirmsWithSweetAlert, WithFileUploads, WithPagination;

    // The same doc_type values pdf-markdown-pipeline's own Document::DOCUMENT_TYPES
    // labels (~/Sites/pdf-markdown-pipeline/app/Models/Document.php) — this corpus is
    // synced from there, so a code here is always one of that fixed set.
    private const DOC_TYPE_LABELS = [
        'go' => 'Government Order',
        'policy' => 'Policy',
        'notice' => 'Notice',
        'court_order' => 'Court Order',
        'service_code' => 'Service Code',
        'rule' => 'Rule',
        'rule_amendment' => 'Amendment to Rule',
        'other' => 'Other',
    ];

    private const CORPUS_PER_PAGE = 20;

    #[Validate('nullable|file|extensions:md|max:2048')]
    public $file = null;

    public string $title = '';

    public string $corpusSearch = '';

    /** @var array<int, array<string, mixed>>|null */
    public ?array $corpusResults = null;

    public bool $corpusUnavailable = false;

    public function mount(): void
    {
        abort_unless(auth()->user()->hasPrivilege('kb.manage'), 403);
    }

    public function upload(): void
    {
        abort_unless(auth()->user()->hasPrivilege('kb.manage'), 403);

        $this->validate([
            'file' => 'required|file|extensions:md|max:2048',
            'title' => 'required|string|max:255',
        ]);

        $contents = file_get_contents($this->file->getRealPath());

        if (! mb_check_encoding($contents, 'UTF-8')) {
            $this->addError('file', 'The file must be valid UTF-8 text.');

            return;
        }

        // Slugified, never the client's original filename — same "don't trust the client
        // filename for the storage path" rule pdf-markdown-pipeline's uploads follow.
        $storedName = Str::slug($this->title).'-'.Str::random(8).'.md';

        try {
            DB::transaction(function () use ($storedName, $contents) {
                $path = Storage::disk('kb-uploads')->put($storedName, $contents) ? $storedName : null;

                KbUpload::create([
                    'uploaded_by' => auth()->id(),
                    'original_name' => $this->file->getClientOriginalName(),
                    'title' => $this->title,
                    'status' => KbUpload::STATUS_PENDING,
                    'origin_ref' => $path,
                ]);
            });

            flash()->success("\"{$this->title}\" uploaded — it will be ingested on the next sync.");
            $this->reset(['file', 'title']);
        } catch (\Throwable $e) {
            Log::error('KnowledgeBaseIndex::upload failed', ['error' => $e->getMessage()]);
            flash()->error('Failed to upload the file. Please try again.');
        }
    }

    public function withdraw(string $uploadId): void
    {
        abort_unless(auth()->user()->hasPrivilege('kb.manage'), 403);

        $upload = KbUpload::findOrFail($uploadId);

        DB::transaction(fn () => $upload->update(['status' => KbUpload::STATUS_WITHDRAWN]));

        flash()->success("\"{$upload->title}\" withdrawn.");
    }

    public function searchCorpus(): void
    {
        try {
            $this->corpusResults = app(OrchestratorClient::class)->kbSearch($this->corpusSearch);
            $this->corpusUnavailable = false;
        } catch (ConnectionException|\Throwable $e) {
            Log::error('KnowledgeBaseIndex::searchCorpus failed', ['error' => $e->getMessage()]);
            $this->corpusUnavailable = true;
        }
    }

    public function docTypeLabel(?string $type): string
    {
        if (! $type) {
            return '—';
        }

        return self::DOC_TYPE_LABELS[$type] ?? Str::headline($type);
    }

    public function render()
    {
        $uploads = KbUpload::with('uploader')->latest()->paginate(10);

        $corpus = null;
        $corpusPaginator = null;
        if (! $this->corpusUnavailable) {
            try {
                $page = Paginator::resolveCurrentPage('corpus_page');
                $corpus = app(OrchestratorClient::class)->kbDocuments($page, self::CORPUS_PER_PAGE);
                $corpusPaginator = new LengthAwarePaginator(
                    $corpus['documents'] ?? [],
                    $corpus['total'] ?? 0,
                    self::CORPUS_PER_PAGE,
                    $page,
                    ['pageName' => 'corpus_page']
                );
            } catch (ConnectionException|\Throwable $e) {
                Log::error('KnowledgeBaseIndex::render kbDocuments failed', ['error' => $e->getMessage()]);
                $this->corpusUnavailable = true;
            }
        }

        return view('livewire.admin.knowledge-base-index', [
            'uploads' => $uploads,
            'corpus' => $corpus,
            'corpusPaginator' => $corpusPaginator,
        ])->layout('components.layout', ['pageTitle' => 'Knowledge base', 'title' => 'Knowledge base']);
    }
}
