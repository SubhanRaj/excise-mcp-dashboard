<?php

namespace Tests\Feature\Admin;

use App\Livewire\Admin\SchemaNotesIndex;
use App\Models\SchemaNote;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Livewire\Livewire;
use Tests\TestCase;

class SchemaNotesIndexTest extends TestCase
{
    use RefreshDatabase;

    private function fakeTable(): array
    {
        return [
            'name' => 'districts',
            'display_name' => 'Districts',
            'summary' => 'The 75 UP districts, grouped into divisions and zones.',
            'note' => '75 UP districts...',
            'columns' => [
                ['name' => 'id', 'data_type' => 'bigint', 'note' => null],
                ['name' => 'name', 'data_type' => 'citext', 'note' => null],
            ],
        ];
    }

    public function test_a_non_privileged_user_is_forbidden(): void
    {
        $user = User::factory()->create(['role' => 'Analyst']);

        Livewire::actingAs($user)->test(SchemaNotesIndex::class)
            ->assertForbidden();
    }

    public function test_an_admin_sees_the_schema(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);

        Http::fake(['*/schema/tables*' => Http::response(['tables' => [$this->fakeTable()]], 200)]);

        Livewire::actingAs($admin)->test(SchemaNotesIndex::class)
            ->assertSee('Districts')
            ->assertSee('analytics.districts');
    }

    public function test_an_unreachable_orchestrator_shows_the_fallback_banner(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);

        Http::fake(['*/schema/tables*' => Http::response('', 502)]);

        Livewire::actingAs($admin)->test(SchemaNotesIndex::class)
            ->assertSee('The orchestrator is unreachable');
    }

    public function test_saving_a_table_note_persists_it(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);

        Http::fake(['*/schema/tables*' => Http::response(['tables' => [$this->fakeTable()]], 200)]);

        Livewire::actingAs($admin)->test(SchemaNotesIndex::class)
            ->set('notes.districts.__table__', '75 UP districts, one row each.')
            ->set('notes.districts.name', "the district's display name")
            ->call('saveTable', 'districts');

        $this->assertDatabaseHas('schema_notes', [
            'table_name' => 'districts',
            'column_name' => '',
            'note' => '75 UP districts, one row each.',
        ]);
        $this->assertDatabaseHas('schema_notes', [
            'table_name' => 'districts',
            'column_name' => 'name',
            'note' => "the district's display name",
        ]);
    }

    public function test_clearing_a_note_deletes_it(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);
        SchemaNote::create(['table_name' => 'districts', 'column_name' => 'name', 'note' => 'old note']);

        Http::fake(['*/schema/tables*' => Http::response(['tables' => [$this->fakeTable()]], 200)]);

        Livewire::actingAs($admin)->test(SchemaNotesIndex::class)
            ->set('notes.districts.name', '')
            ->call('saveTable', 'districts');

        $this->assertDatabaseMissing('schema_notes', ['table_name' => 'districts', 'column_name' => 'name']);
    }

    public function test_toggle_sample_fetches_and_hides_rows(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);

        Http::fake([
            '*/schema/tables/districts/sample*' => Http::response(['rows' => [['id' => '1', 'name' => 'Lucknow']]], 200),
            '*/schema/tables*' => Http::response(['tables' => [$this->fakeTable()]], 200),
        ]);

        Livewire::actingAs($admin)->test(SchemaNotesIndex::class)
            ->call('toggleSample', 'districts')
            ->assertSee('Lucknow')
            ->call('toggleSample', 'districts')
            ->assertDontSee('Lucknow');
    }
}
