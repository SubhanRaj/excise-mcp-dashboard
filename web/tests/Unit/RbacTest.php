<?php

namespace Tests\Unit;

use App\Models\Designation;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class RbacTest extends TestCase
{
    use RefreshDatabase;

    public function test_admin_has_every_privilege_without_being_listed(): void
    {
        $admin = User::factory()->create(['role' => 'Admin', 'privileges' => []]);

        $this->assertTrue($admin->isAdmin());
        $this->assertTrue($admin->hasPrivilege('kb.manage'));
        $this->assertTrue($admin->hasPrivilege('anything.not.in.the.list'));
    }

    public function test_analyst_has_only_listed_privileges(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst', 'privileges' => ['kb.manage']]);

        $this->assertFalse($analyst->isAdmin());
        $this->assertTrue($analyst->hasPrivilege('kb.manage'));
        $this->assertFalse($analyst->hasPrivilege('users.manage'));
    }

    public function test_wildcard_privilege_grants_everything(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst', 'privileges' => ['*']]);

        $this->assertTrue($analyst->hasPrivilege('users.manage'));
        $this->assertTrue($analyst->hasPrivilege('activity-logs.view'));
    }

    public function test_analyst_with_no_privileges_has_none(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst', 'privileges' => null]);

        $this->assertFalse($analyst->hasPrivilege('kb.manage'));
    }

    /**
     * A designation's default_privileges copies onto the user at creation time
     * (web/plan/webui.md §6). Editing the user's privileges afterward doesn't stay linked
     * back to the designation.
     */
    public function test_designation_default_privileges_is_a_copied_preset_not_a_live_link(): void
    {
        $designation = Designation::create([
            'name' => 'District Excise Officer',
            'slug' => 'district-excise-officer',
            'default_privileges' => ['kb.manage'],
            'sort_order' => 0,
        ]);

        $user = User::factory()->create([
            'role' => 'Analyst',
            'designation_id' => $designation->id,
            'privileges' => $designation->default_privileges,
        ]);

        $this->assertSame(['kb.manage'], $user->fresh()->privileges);

        $designation->update(['default_privileges' => ['kb.manage', 'users.manage']]);

        $this->assertSame(['kb.manage'], $user->fresh()->privileges);
    }
}
