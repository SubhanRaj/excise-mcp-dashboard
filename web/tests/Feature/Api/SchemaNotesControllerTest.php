<?php

namespace Tests\Feature\Api;

use App\Models\SchemaNote;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * The one route the orchestrator calls into web/ (CLAUDE.md §Data dictionary) —
 * gated by VerifyOrchestratorToken instead of session auth, since the caller is a
 * server-to-server process with no logged-in user.
 */
class SchemaNotesControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_a_request_with_no_token_is_rejected(): void
    {
        $this->getJson('/api/schema-notes')->assertUnauthorized();
    }

    public function test_a_request_with_the_wrong_token_is_rejected(): void
    {
        $this->withToken('not-the-shared-secret')
            ->getJson('/api/schema-notes')
            ->assertUnauthorized();
    }

    public function test_the_shared_token_returns_every_note(): void
    {
        SchemaNote::create(['table_name' => 'districts', 'column_name' => '', 'note' => 'a table note']);
        SchemaNote::create(['table_name' => 'districts', 'column_name' => 'name', 'note' => 'a column note']);

        $this->withToken(config('services.orchestrator.token'))
            ->getJson('/api/schema-notes')
            ->assertOk()
            ->assertJsonCount(2)
            ->assertJsonFragment(['table_name' => 'districts', 'column_name' => '', 'note' => 'a table note'])
            ->assertJsonFragment(['table_name' => 'districts', 'column_name' => 'name', 'note' => 'a column note']);
    }
}
