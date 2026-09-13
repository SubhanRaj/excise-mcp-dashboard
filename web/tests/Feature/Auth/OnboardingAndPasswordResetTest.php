<?php

namespace Tests\Feature\Auth;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Facades\Password;
use Illuminate\Support\Facades\URL;
use Tests\TestCase;

class OnboardingAndPasswordResetTest extends TestCase
{
    use RefreshDatabase;

    public function test_a_valid_onboarding_link_activates_the_account(): void
    {
        $user = User::factory()->unverified()->create(['password' => null]);
        $url = URL::temporarySignedRoute('onboarding.show', now()->addHours(72), ['user' => $user->id]);

        $response = $this->post($url, [
            'password' => 'A-Str0ng!Pass',
            'password_confirmation' => 'A-Str0ng!Pass',
        ]);

        $response->assertRedirect(route('login'));
        $this->assertNotNull($user->fresh()->email_verified_at);
        $this->assertNotNull($user->fresh()->password);
    }

    public function test_an_already_active_account_cannot_be_onboarded_again(): void
    {
        $user = User::factory()->create();
        $url = URL::temporarySignedRoute('onboarding.show', now()->addHours(72), ['user' => $user->id]);

        $response = $this->get($url);

        $response->assertRedirect(route('login'));
    }

    public function test_forgot_password_always_reports_success_regardless_of_email(): void
    {
        Mail::fake();

        $response = $this->post('/forgot-password', ['email' => 'nobody@example.com']);

        $response->assertRedirect(route('login'));
    }

    public function test_a_valid_reset_link_updates_the_password(): void
    {
        $user = User::factory()->create();
        $token = Password::createToken($user);

        $response = $this->post('/reset-password', [
            'token' => $token,
            'email' => $user->email,
            'password' => 'Another-Str0ng!Pass',
            'password_confirmation' => 'Another-Str0ng!Pass',
        ]);

        $response->assertRedirect(route('login'));
        $this->assertTrue(Hash::check('Another-Str0ng!Pass', $user->fresh()->password));
    }
}
