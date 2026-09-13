<?php

namespace App\Http\Controllers\Auth;

use App\Actions\Fortify\PasswordValidationRules;
use App\Http\Controllers\Controller;
use App\Models\User;
use Illuminate\Auth\Events\PasswordReset;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Password;
use Illuminate\Support\Str;
use Illuminate\Validation\ValidationException;
use Illuminate\View\View;

/**
 * Forgot / reset password on Laravel's core Password broker — password_reset_tokens table,
 * single-use hashed token, 60-minute expiry — with this app's branded views and mail
 * (User::sendPasswordResetNotification -> App\Mail\ResetPassword) instead of Fortify's.
 * Success never auto-authenticates: the user lands back on /login and re-enters the normal
 * email + password + OTP flow.
 */
class ForgotPasswordController extends Controller
{
    use PasswordValidationRules;

    public function showRequestForm(): View
    {
        return view('auth.forgot-password');
    }

    /**
     * Always redirects with the same message whether or not the email matches an account —
     * Password::sendResetLink() no-ops silently for an unknown email, and a different message
     * here would let an attacker enumerate accounts.
     */
    public function sendResetLink(Request $request): RedirectResponse
    {
        $request->validate(['email' => ['required', 'email']]);

        Password::sendResetLink($request->only('email'));

        flash()->success('If an account exists for that email, a password reset link is on its way.');

        return redirect()->route('login');
    }

    public function showResetForm(Request $request, string $token): View
    {
        return view('auth.reset-password', [
            'token' => $token,
            'email' => $request->query('email', ''),
        ]);
    }

    public function reset(Request $request): RedirectResponse
    {
        $validated = $request->validate([
            'token' => ['required'],
            'email' => ['required', 'email'],
            'password' => $this->passwordRules(),
        ]);

        $status = Password::reset($validated, function (User $user, string $password) {
            $user->forceFill([
                'password' => $password,
                'email_verified_at' => $user->email_verified_at ?? now(),
            ])->setRememberToken(Str::random(60));

            $user->save();

            event(new PasswordReset($user));
        });

        if ($status !== Password::PASSWORD_RESET) {
            throw ValidationException::withMessages(['email' => [__($status)]]);
        }

        flash()->success('Your password has been reset — please sign in.');

        return redirect()->route('login');
    }
}
