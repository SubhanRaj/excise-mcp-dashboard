<?php

namespace App\Livewire\Admin;

use App\Models\SchemaNote;
use App\Services\OrchestratorClient;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Log;
use Livewire\Component;

/**
 * The data dictionary: every analytics.* table and column (from the orchestrator's
 * GET /schema/tables — web/ never reaches Postgres directly) alongside an admin-editable
 * note per table/column, stored in web/'s own schema_notes table. The orchestrator reads
 * these back over GET /api/schema-notes and folds them into the SQL-planning prompt next
 * to schema_card.py's own VIEW_NOTES (CLAUDE.md §Data dictionary). A "__table__" key in
 * $notes[$table] holds the table-level note; every other key is a column name.
 */
class SchemaNotesIndex extends Component
{
    private const TABLE_NOTE_KEY = '__table__';

    public bool $unavailable = false;

    /** @var array<int, array<string, mixed>> */
    public array $tables = [];

    /** @var array<string, array<string, string>> */
    public array $notes = [];

    public ?string $expandedTable = null;

    /** @var array<int, array<string, mixed>> */
    public array $sample = [];

    public function mount(): void
    {
        abort_unless(auth()->user()->hasPrivilege('schema.manage'), 403);

        foreach (SchemaNote::all() as $note) {
            $this->notes[$note->table_name][$note->column_name === '' ? self::TABLE_NOTE_KEY : $note->column_name] = $note->note;
        }
    }

    public function toggleSample(string $table): void
    {
        if ($this->expandedTable === $table) {
            $this->expandedTable = null;
            $this->sample = [];

            return;
        }

        $this->expandedTable = $table;

        try {
            $this->sample = app(OrchestratorClient::class)->schemaSample($table);
        } catch (ConnectionException|\Throwable $e) {
            Log::error('SchemaNotesIndex::toggleSample failed', ['table' => $table, 'error' => $e->getMessage()]);
            $this->sample = [];
        }
    }

    public function saveTable(string $table): void
    {
        abort_unless(auth()->user()->hasPrivilege('schema.manage'), 403);

        foreach ($this->notes[$table] ?? [] as $key => $note) {
            $columnName = $key === self::TABLE_NOTE_KEY ? '' : $key;
            $note = trim($note);

            if ($note === '') {
                SchemaNote::query()->where('table_name', $table)->where('column_name', $columnName)->delete();

                continue;
            }

            SchemaNote::query()->updateOrCreate(
                ['table_name' => $table, 'column_name' => $columnName],
                ['note' => $note]
            );
        }
    }

    public function render()
    {
        try {
            $this->tables = app(OrchestratorClient::class)->schemaTables();
            $this->unavailable = false;
        } catch (ConnectionException|\Throwable $e) {
            Log::error('SchemaNotesIndex::render failed', ['error' => $e->getMessage()]);
            $this->unavailable = true;
        }

        return view('livewire.admin.schema-notes-index')
            ->layout('components.layout', ['pageTitle' => 'Data dictionary', 'title' => 'Data dictionary']);
    }
}
