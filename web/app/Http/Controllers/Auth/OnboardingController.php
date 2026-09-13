<?php

namespace App\Http\Controllers\Auth;

use App\Actions\Fortify\PasswordValidationRules;
use App\Http\Controllers\Controller;
use App\Models\User;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\View\View;

/**
 * Admin-created accounts are passwordless (users.password nullable) until the user opens the
 * signed, single-use, 72-hour link mailed by Admin -> Users and sets a password here. A set
 * email_verified_at doubles as the "already activated" gate.
 */
class OnboardingController extends Controller
{
    use PasswordValidationRules;

    public function show(Request $request, User $user): View|RedirectResponse
    {
        if ($user->email_verified_at !== null) {
            flash()->success('This account is already active — please sign in.');

            return redirect()->route('login');
        }

        return view('auth.onboarding', ['user' => $user, 'signedUrl' => $request->fullUrl()]);
    }

    public function store(Request $request, User $user): RedirectResponse
    {
        if ($user->email_verified_at !== null) {
            flash()->success('This account is already active — please sign in.');

            return redirect()->route('login');
        }

        $validated = $request->validate(['password' => $this->passwordRules()]);

        $user->forceFill([
            'password' => $validated['password'],
            'email_verified_at' => now(),
        ])->save();

        flash()->success('Account activated — please sign in with your new password.');

        return redirect()->route('login');
    }
}
