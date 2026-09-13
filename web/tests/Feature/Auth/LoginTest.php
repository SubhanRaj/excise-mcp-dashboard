<?php

namespace Tests\Feature\Auth;

use App\Mail\LoginOtp;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Mail;
use Tests\TestCase;

class LoginTest extends TestCase
{
    use RefreshDatabase;

    public function test_correct_credentials_send_an_otp_and_do_not_authenticate_yet(): void
    {
        Mail::fake();
        $user = User::factory()->create(['password' => Hash::make('correct-password')]);

        $response = $this->post('/login', ['email' => $user->email, 'password' => 'correct-password']);

        $response->assertRedirect(route('otp.show'));
        $this->assertGuest();
        Mail::assertSent(LoginOtp::class);
    }

    public function test_wrong_password_is_rejected(): void
    {
        $user = User::factory()->create(['password' => Hash::make('correct-password')]);

        $response = $this->post('/login', ['email' => $user->email, 'password' => 'wrong-password']);

        $response->assertSessionHasErrors('email');
        $this->assertGuest();
    }

    public function test_unverified_account_cannot_start_login(): void
    {
        $user = User::factory()->unverified()->create(['password' => Hash::make('correct-password')]);

        $response = $this->post('/login', ['email' => $user->email, 'password' => 'correct-password']);

        $response->assertSessionHasErrors('email');
    }

    public function test_wrong_otp_is_rejected(): void
    {
        $user = User::factory()->create();
        $this->withSession(['login.id' => $user->id, 'otp.code' => '123456', 'otp.expires_at' => now()->addMinutes(10)]);

        $response = $this->post('/login/otp/verify', ['code' => '999999']);

        $response->assertSessionHasErrors('code');
        $this->assertGuest();
    }

    public function test_expired_otp_is_rejected(): void
    {
        $user = User::factory()->create();
        $this->withSession(['login.id' => $user->id, 'otp.code' => '123456', 'otp.expires_at' => now()->subMinute()]);

        $response = $this->post('/login/otp/verify', ['code' => '123456']);

        $response->assertSessionHasErrors('code');
        $this->assertGuest();
    }

    public function test_correct_otp_authenticates(): void
    {
        $user = User::factory()->create();
        $this->withSession(['login.id' => $user->id, 'otp.code' => '123456', 'otp.expires_at' => now()->addMinutes(10)]);

        $response = $this->post('/login/otp/verify', ['code' => '123456']);

        $response->assertRedirect(route('ask'));
        $this->assertAuthenticatedAs($user);
    }

    public function test_an_unauthenticated_request_to_a_protected_route_redirects_to_login(): void
    {
        $response = $this->get('/ask');

        $response->assertRedirect(route('login'));
    }
}
