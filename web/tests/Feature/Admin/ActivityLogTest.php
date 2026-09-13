<?php

namespace Tests\Feature\Admin;

use App\Models\ActivityLog;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ActivityLogTest extends TestCase
{
    use RefreshDatabase;

    public function test_a_non_privileged_user_is_forbidden(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst', 'privileges' => []]);

        $this->actingAs($analyst)->get(route('admin.activity-logs.index'))->assertForbidden();
    }

    public function test_an_admin_can_view_the_activity_log(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);
        ActivityLog::create(['action' => 'auth.login', 'ip_address' => '127.0.0.1', 'created_at' => now()]);

        $this->actingAs($admin)->get(route('admin.activity-logs.index'))
            ->assertOk()
            ->assertSee('auth.login');
    }

    public function test_a_non_get_request_by_an_authenticated_user_writes_an_activity_log_row(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);

        $this->actingAs($admin)->post('/logout');

        $this->assertDatabaseHas('activity_logs', ['action' => 'auth.logout', 'user_id' => $admin->id]);
    }
}
