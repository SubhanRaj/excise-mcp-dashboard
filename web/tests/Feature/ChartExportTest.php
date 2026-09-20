<?php

namespace Tests\Feature;

use App\Models\ChartArtifact;
use App\Models\Query;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ChartExportTest extends TestCase
{
    use RefreshDatabase;

    public function test_the_owner_downloads_a_rendered_png(): void
    {
        $user = User::factory()->create();
        $query = Query::create(['user_id' => $user->id, 'prompt' => 'test', 'status' => 'complete']);
        $artifact = ChartArtifact::create([
            'owner_type' => Query::class,
            'owner_id' => $query->id,
            'spec' => ['data' => [], 'layout' => ['title' => 'Test']],
        ]);

        Http::fake(['*/chart/render' => Http::response('fake-png-bytes', 200)]);

        $response = $this->actingAs($user)
            ->get(route('chart-artifacts.export', ['chartArtifact' => $artifact->id, 'format' => 'png']));

        $response->assertOk();
        $response->assertHeader('Content-Type', 'image/png');
        $this->assertSame('fake-png-bytes', $response->getContent());
    }

    public function test_another_users_chart_is_forbidden(): void
    {
        $owner = User::factory()->create();
        $intruder = User::factory()->create();
        $query = Query::create(['user_id' => $owner->id, 'prompt' => 'test', 'status' => 'complete']);
        $artifact = ChartArtifact::create([
            'owner_type' => Query::class,
            'owner_id' => $query->id,
            'spec' => ['data' => [], 'layout' => []],
        ]);

        $this->actingAs($intruder)
            ->get(route('chart-artifacts.export', ['chartArtifact' => $artifact->id, 'format' => 'png']))
            ->assertForbidden();
    }

    public function test_an_unknown_format_is_rejected(): void
    {
        $user = User::factory()->create();
        $query = Query::create(['user_id' => $user->id, 'prompt' => 'test', 'status' => 'complete']);
        $artifact = ChartArtifact::create([
            'owner_type' => Query::class,
            'owner_id' => $query->id,
            'spec' => ['data' => [], 'layout' => []],
        ]);

        $this->actingAs($user)
            ->get(route('chart-artifacts.export', ['chartArtifact' => $artifact->id, 'format' => 'gif']))
            ->assertStatus(422);
    }
}
