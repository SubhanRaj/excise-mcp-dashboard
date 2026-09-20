<?php

namespace Tests\Feature\Admin;

use App\Livewire\Admin\EtlRunsIndex;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Livewire\Livewire;
use Tests\TestCase;

class EtlRunsIndexTest extends TestCase
{
    use RefreshDatabase;

    private function fakeRun(): array
    {
        return [
            'id' => 1,
            'source' => 'iescms_dispatch',
            'source_ref' => 'august-2026-lucknow.csv',
            'report_period' => '2026-08-01',
            'started_at' => now()->toIso8601String(),
            'finished_at' => now()->toIso8601String(),
            'status' => 'ok',
            'rows_seen' => 100,
            'rows_upserted' => 99,
            'rows_quarantined' => 1,
            'error' => null,
        ];
    }

    public function test_a_non_privileged_user_is_forbidden(): void
    {
        $user = User::factory()->create(['role' => 'Analyst']);

        Livewire::actingAs($user)->test(EtlRunsIndex::class)
            ->assertForbidden();
    }

    public function test_an_admin_sees_ingestion_runs(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);

        Http::fake([
            '*/etl/runs*' => Http::response(['runs' => [$this->fakeRun()], 'total' => 1], 200),
        ]);

        Livewire::actingAs($admin)->test(EtlRunsIndex::class)
            ->assertSee('iescms_dispatch')
            ->assertSee('august-2026-lucknow.csv');
    }

    public function test_a_granted_analyst_can_view_it_too(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst', 'privileges' => ['etl.view']]);

        Http::fake([
            '*/etl/runs*' => Http::response(['runs' => [$this->fakeRun()], 'total' => 1], 200),
        ]);

        Livewire::actingAs($analyst)->test(EtlRunsIndex::class)
            ->assertSee('iescms_dispatch');
    }

    public function test_an_unreachable_orchestrator_shows_the_fallback_banner(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);

        Http::fake(['*/etl/runs*' => Http::response('', 502)]);

        Livewire::actingAs($admin)->test(EtlRunsIndex::class)
            ->assertSee('The orchestrator is unreachable');
    }

    public function test_view_quarantine_toggles_the_reasons_for_a_run(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);

        Http::fake([
            '*/etl/runs*' => Http::response(['runs' => [$this->fakeRun()], 'total' => 1], 200),
            '*/etl/quarantine*' => Http::response([
                'rows' => [['id' => 1, 'run_id' => 1, 'raw_row' => ['district' => '???'], 'reason' => 'unresolvable district alias', 'created_at' => now()->toIso8601String()]],
                'total' => 1,
            ], 200),
        ]);

        Livewire::actingAs($admin)->test(EtlRunsIndex::class)
            ->call('viewQuarantine', 1)
            ->assertSee('unresolvable district alias');
    }
}
