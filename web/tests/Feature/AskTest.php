<?php

namespace Tests\Feature;

use App\Jobs\RunExciseQuery;
use App\Livewire\Ask;
use App\Models\ChartArtifact;
use App\Models\Query;
use App\Models\User;
use App\Services\OrchestratorClient;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Bus;
use Illuminate\Support\Facades\Http;
use Livewire\Livewire;
use Tests\TestCase;

class AskTest extends TestCase
{
    use RefreshDatabase;

    public function test_submitting_a_question_creates_a_pending_query_row_and_dispatches_the_job(): void
    {
        Bus::fake();
        $user = User::factory()->create();

        Livewire::actingAs($user)->test(Ask::class)
            ->set('prompt', 'How many districts are in each zone?')
            ->call('submit');

        $this->assertDatabaseHas('queries', [
            'user_id' => $user->id,
            'prompt' => 'How many districts are in each zone?',
            'status' => 'pending',
        ]);
        Bus::assertDispatched(RunExciseQuery::class);
    }

    public function test_a_blank_question_is_rejected(): void
    {
        $user = User::factory()->create();

        Livewire::actingAs($user)->test(Ask::class)
            ->set('prompt', '')
            ->call('submit')
            ->assertHasErrors('prompt');
    }

    public function test_the_job_persists_a_successful_result_and_chart_artifact(): void
    {
        $user = User::factory()->create();
        $query = Query::create(['user_id' => $user->id, 'prompt' => 'test question', 'status' => 'pending']);

        Http::fake([
            '*/query' => Http::response(
                $this->ndjson([
                    ['stage' => ['name' => 'plan_sql', 'status' => 'ok']],
                    ['stage' => ['name' => 'run_sql', 'status' => 'ok']],
                    ['result' => [
                        'request_id' => 'req-1',
                        'sql' => 'SELECT 1',
                        'row_count' => 1,
                        'rows_preview' => [['count' => 1]],
                        'chart' => ['plotly_json' => json_encode(['data' => [], 'layout' => []])],
                        'summary' => 'There is 1 row.',
                        'engine' => 'python',
                        'model' => 'qwen2.5-coder',
                        'timings_ms' => ['run_sql' => 12],
                    ]],
                ]),
                200,
            ),
        ]);

        (new RunExciseQuery($query->id))->handle(app(OrchestratorClient::class));

        $query->refresh();
        $this->assertSame('complete', $query->status);
        $this->assertSame('SELECT 1', $query->sql);
        $this->assertSame(1, $query->row_count);
        $this->assertSame('There is 1 row.', $query->summary);
        $this->assertDatabaseHas('chart_artifacts', [
            'owner_type' => Query::class,
            'owner_id' => $query->id,
        ]);
        $this->assertNotNull(ChartArtifact::where('owner_id', $query->id)->first()->spec);
    }

    public function test_the_job_marks_a_query_failed_on_an_orchestrator_error(): void
    {
        $user = User::factory()->create();
        $query = Query::create(['user_id' => $user->id, 'prompt' => 'bad question', 'status' => 'pending']);

        Http::fake([
            '*/query' => Http::response(
                $this->ndjson([
                    ['stage' => ['name' => 'plan_sql', 'status' => 'running']],
                    ['error' => 'the model produced invalid SQL', 'request_id' => 'req-2', 'stage' => 'guard_sql'],
                ]),
                200,
            ),
        ]);

        (new RunExciseQuery($query->id))->handle(app(OrchestratorClient::class));

        $query->refresh();
        $this->assertSame('failed', $query->status);
        $this->assertSame('guard_sql', $query->current_stage);
        $this->assertSame('the model produced invalid SQL', $query->error_message);
    }

    public function test_the_stream_endpoint_returns_status_and_current_stage(): void
    {
        $user = User::factory()->create();
        $query = Query::create([
            'user_id' => $user->id, 'prompt' => 'x', 'status' => 'running', 'current_stage' => 'run_sql',
        ]);

        $this->actingAs($user)->getJson(route('ask.stream', $query))
            ->assertOk()
            ->assertJson(['status' => 'running', 'current_stage' => 'run_sql']);
    }

    public function test_a_user_cannot_poll_another_users_query(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $query = Query::create(['user_id' => $owner->id, 'prompt' => 'x', 'status' => 'pending']);

        $this->actingAs($other)->getJson(route('ask.stream', $query))->assertForbidden();
    }

    /**
     * @param  list<array<string, mixed>>  $events
     */
    private function ndjson(array $events): string
    {
        return implode("\n", array_map(fn (array $e) => json_encode($e), $events))."\n";
    }
}
