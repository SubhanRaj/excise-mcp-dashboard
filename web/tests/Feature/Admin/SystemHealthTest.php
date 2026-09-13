<?php

namespace Tests\Feature\Admin;

use App\Models\Query;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SystemHealthTest extends TestCase
{
    use RefreshDatabase;

    public function test_a_non_privileged_user_is_forbidden(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst', 'privileges' => []]);

        $this->actingAs($analyst)->get(route('admin.system-health.index'))->assertForbidden();
    }

    public function test_an_admin_can_view_it_and_it_totals_token_usage_by_model(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);
        $other = User::factory()->create();
        Query::create([
            'user_id' => $other->id, 'prompt' => 'x', 'status' => 'complete',
            'model' => 'qwen2.5-coder', 'prompt_tokens' => 100, 'completion_tokens' => 20,
        ]);
        Query::create([
            'user_id' => $other->id, 'prompt' => 'y', 'status' => 'complete',
            'model' => 'qwen2.5-coder', 'prompt_tokens' => 50, 'completion_tokens' => 10,
        ]);

        $this->actingAs($admin)->get(route('admin.system-health.index'))
            ->assertOk()
            ->assertSee('qwen2.5-coder')
            ->assertSeeText('150') // summed prompt tokens
            ->assertSeeText('30'); // summed completion tokens
    }

    public function test_an_analyst_with_the_system_monitor_privilege_can_view_it(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst', 'privileges' => ['system.monitor']]);

        $this->actingAs($analyst)->get(route('admin.system-health.index'))->assertOk();
    }
}
