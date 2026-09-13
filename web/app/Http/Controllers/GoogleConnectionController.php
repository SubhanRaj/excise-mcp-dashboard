<?php

namespace App\Http\Controllers;

use App\Models\GoogleConnection;
use Illuminate\Http\RedirectResponse;
use Illuminate\Support\Facades\Log;
use Laravel\Socialite\Facades\Socialite;

/**
 * An OAuth redirect is a full browser navigation to Google and back — Livewire can't
 * intercept it, so this stays a plain controller (web/plan/webui.md §5). The Connected
 * sources screen itself (list, disconnect) is the Livewire GoogleConnectionIndex.
 */
class GoogleConnectionController extends Controller
{
    private const SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/documents.readonly',
    ];

    public function connect(): RedirectResponse
    {
        abort_unless(auth()->user()->hasPrivilege('google.manage'), 403);

        return Socialite::driver('google')
            ->scopes(self::SCOPES)
            ->with(['access_type' => 'offline', 'prompt' => 'consent'])
            ->redirect();
    }

    public function callback(): RedirectResponse
    {
        abort_unless(auth()->user()->hasPrivilege('google.manage'), 403);

        try {
            $googleUser = Socialite::driver('google')->user();
        } catch (\Throwable $e) {
            Log::error('GoogleConnectionController::callback failed', ['error' => $e->getMessage()]);
            flash()->error('Google sign-in failed. Please try again.');

            return redirect()->route('admin.google.index');
        }

        // access_type=offline + prompt=consent guarantees a refresh token on first
        // consent; Google omits it on a repeat consent for the same client+account, so a
        // reconnect keeps the previously stored one rather than overwriting it with null.
        GoogleConnection::updateOrCreate(
            ['user_id' => auth()->id(), 'google_sub' => $googleUser->getId()],
            array_filter([
                'email' => $googleUser->getEmail(),
                'scopes' => self::SCOPES,
                'refresh_token' => $googleUser->refreshToken,
                'revoked_at' => null,
            ], fn ($v) => $v !== null)
        );

        flash()->success('Google account connected.');

        return redirect()->route('admin.google.index');
    }
}
