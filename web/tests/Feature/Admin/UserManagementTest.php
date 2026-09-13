<?php

namespace Tests\Feature\Admin;

use App\Livewire\Admin\UserForm;
use App\Livewire\Admin\UserIndex;
use App\Mail\AccountOnboarding;
use App\Models\Designation;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Mail;
use Livewire\Livewire;
use Tests\TestCase;

class UserManagementTest extends TestCase
{
    use RefreshDatabase;

    public function test_a_non_privileged_user_is_forbidden(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst', 'privileges' => []]);

        $this->actingAs($analyst)->get(route('admin.users.index'))->assertForbidden();
    }

    public function test_an_admin_can_list_users(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);
        User::factory()->count(3)->create();

        $this->actingAs($admin)->get(route('admin.users.index'))->assertOk();
    }

    public function test_creating_a_user_sends_an_onboarding_email_and_leaves_the_account_unverified(): void
    {
        Mail::fake();
        $admin = User::factory()->create(['role' => 'Admin']);

        Livewire::actingAs($admin)->test(UserForm::class)
            ->set('name', 'New Analyst')
            ->set('username', 'new_analyst')
            ->set('email', 'new.analyst@example.com')
            ->set('role', 'Analyst')
            ->call('save')
            ->assertRedirect(route('admin.users.index'));

        $user = User::where('email', 'new.analyst@example.com')->firstOrFail();
        $this->assertNull($user->email_verified_at);
        Mail::assertSent(AccountOnboarding::class);
    }

    public function test_a_designations_default_privileges_preset_onto_the_form_only_on_create(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);
        $designation = Designation::create([
            'name' => 'District Excise Officer', 'slug' => 'deo', 'default_privileges' => ['kb.manage'], 'sort_order' => 0,
        ]);

        Livewire::actingAs($admin)->test(UserForm::class)
            ->set('designationId', $designation->id)
            ->assertSet('privileges', ['kb.manage']);
    }

    public function test_an_admin_cannot_delete_their_own_account(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);

        Livewire::actingAs($admin)->test(UserIndex::class)->call('delete', $admin->id);

        $this->assertNull($admin->fresh()->deleted_at);
    }
}
