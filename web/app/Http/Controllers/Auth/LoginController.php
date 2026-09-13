<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Mail\LoginOtp;
use App\Models\User;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Mail;
use Illuminate\Validation\ValidationException;
use Illuminate\View\View;

class LoginController extends Controller
{
    private const OTP_TTL_MINUTES = 10;

    private const RESEND_COOLDOWN = 45; // seconds

    public function showLogin(): View
    {
        return view('auth.login');
    }

    /**
     * Validates credentials WITHOUT logging in — a session is only ever granted after OTP
     * succeeds in verifyOtp(). Because Auth::login() is never called here, there is no
     * authenticated-but-unverified window for protected routes to accidentally allow through.
     */
    public function login(Request $request): RedirectResponse
    {
        $credentials = $request->validate([
            'email' => ['required', 'email'],
            'password' => ['required', 'string'],
        ]);

        if (! Auth::guard('web')->validate($credentials)) {
            throw ValidationException::withMessages([
                'email' => 'These credentials do not match our records.',
            ]);
        }

        /** @var User $user */
        $user = User::where('email', $credentials['email'])->firstOrFail();

        if ($user->email_verified_at === null) {
            throw ValidationException::withMessages([
                'email' => 'This account is not activated yet — check your email for the activation link.',
            ]);
        }

        $this->issueOtp($request, $user, (bool) $request->boolean('remember'));

        return redirect()->route('otp.show');
    }

    public function showOtp(Request $request): View|RedirectResponse
    {
        if (! $request->session()->has('login.id')) {
            return redirect()->route('login');
        }

        return view('auth.otp');
    }

    public function verifyOtp(Request $request): RedirectResponse
    {
        $request->validate(['code' => ['required', 'digits:6']]);

        $userId = $request->session()->get('login.id');

        if (! $userId) {
            return redirect()->route('login');
        }

        $expiresAt = $request->session()->get('otp.expires_at');
        $storedCode = (string) $request->session()->get('otp.code');

        if (! $expiresAt || now()->greaterThan($expiresAt) || ! hash_equals($storedCode, (string) $request->input('code'))) {
            throw ValidationException::withMessages([
                'code' => 'That code is invalid or has expired.',
            ]);
        }

        $user = User::findOrFail($userId);
        $remember = (bool) $request->session()->get('login.remember');

        $request->session()->forget(['login.id', 'login.remember', 'otp.code', 'otp.expires_at', 'otp.last_sent_at']);

        Auth::login($user, $remember);
        $request->session()->regenerate();

        return redirect()->intended(route('ask'));
    }

    public function resendOtp(Request $request): RedirectResponse
    {
        $userId = $request->session()->get('login.id');

        if (! $userId) {
            return redirect()->route('login');
        }

        $lastSentAt = $request->session()->get('otp.last_sent_at');

        if ($lastSentAt && now()->diffInSeconds($lastSentAt) < self::RESEND_COOLDOWN) {
            flash()->warning('Please wait a moment before requesting another code.');

            return redirect()->route('otp.show');
        }

        $user = User::findOrFail($userId);
        $remember = (bool) $request->session()->get('login.remember');

        $this->issueOtp($request, $user, $remember);

        flash()->success('A new code has been sent.');

        return redirect()->route('otp.show');
    }

    public function logout(Request $request): RedirectResponse
    {
        Auth::guard('web')->logout();
        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return redirect()->route('login');
    }

    private function issueOtp(Request $request, User $user, bool $remember): void
    {
        $code = (string) random_int(100000, 999999);

        $request->session()->put([
            'login.id' => $user->id,
            'login.remember' => $remember,
            'otp.code' => $code,
            'otp.expires_at' => now()->addMinutes(self::OTP_TTL_MINUTES),
            'otp.last_sent_at' => now(),
        ]);

        Mail::to($user->email)->send(new LoginOtp($user, $code, self::OTP_TTL_MINUTES));
    }
}
