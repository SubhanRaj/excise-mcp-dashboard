<?php

namespace Tests\Feature;

use App\Livewire\QueryLedger;
use App\Models\Query;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class QueryLedgerTest extends TestCase
{
    use RefreshDatabase;

    public function test_an_analyst_sees_only_their_own_queries(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst']);
        $other = User::factory()->create(['role' => 'Analyst']);
        Query::create(['user_id' => $analyst->id, 'prompt' => 'mine', 'status' => 'complete']);
        Query::create(['user_id' => $other->id, 'prompt' => 'not mine', 'status' => 'complete']);

        Livewire::actingAs($analyst)->test(QueryLedger::class)
            ->assertSee('mine')
            ->assertDontSee('not mine');
    }

    public function test_an_admin_sees_every_query(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);
        $analyst = User::factory()->create(['role' => 'Analyst']);
        Query::create(['user_id' => $admin->id, 'prompt' => 'admin question', 'status' => 'complete']);
        Query::create(['user_id' => $analyst->id, 'prompt' => 'analyst question', 'status' => 'complete']);

        Livewire::actingAs($admin)->test(QueryLedger::class)
            ->assertSee('admin question')
            ->assertSee('analyst question');
    }

    public function test_search_filters_by_prompt(): void
    {
        $user = User::factory()->create(['role' => 'Analyst']);
        Query::create(['user_id' => $user->id, 'prompt' => 'revenue trend for Lucknow', 'status' => 'complete']);
        Query::create(['user_id' => $user->id, 'prompt' => 'shop count in Kanpur', 'status' => 'complete']);

        Livewire::actingAs($user)->test(QueryLedger::class)
            ->set('search', 'Lucknow')
            ->assertSee('revenue trend for Lucknow')
            ->assertDontSee('shop count in Kanpur');
    }

    public function test_an_unauthenticated_request_is_redirected_to_login(): void
    {
        $this->get(route('ledger'))->assertRedirect(route('login'));
    }
}
