<?php

namespace App\Models;

use App\Mail\ResetPassword;
use Database\Factories\UserFactory;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Attributes\Hidden;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Foundation\Auth\User as Authenticatable;
use Illuminate\Notifications\Notifiable;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Str;

#[Fillable(['name', 'username', 'email', 'mobile', 'password', 'role', 'post', 'designation_id', 'privileges', 'ui_prefs', 'email_verified_at'])]
#[Hidden(['password', 'remember_token'])]
class User extends Authenticatable
{
    /** @use HasFactory<UserFactory> */
    use HasFactory, Notifiable, SoftDeletes;

    /**
     * The privilege strings every admin write re-checks with abort_unless(), matching
     * SECURITY.md §3 — livewire/update skips route middleware, so mount-time gating alone
     * isn't enough. Keep in sync with web/plan/webui.md §6.
     */
    public const PRIVILEGES = [
        'kb.manage',
        'google.manage',
        'users.manage',
        'activity-logs.view',
    ];

    public const ROLES = ['Admin', 'Analyst'];

    protected function casts(): array
    {
        return [
            'email_verified_at' => 'datetime',
            'password' => 'hashed',
            'privileges' => 'array',
            'ui_prefs' => 'array',
        ];
    }

    public function designation(): BelongsTo
    {
        return $this->belongsTo(Designation::class)->withTrashed();
    }

    public function isAdmin(): bool
    {
        return $this->role === 'Admin';
    }

    public function hasPrivilege(string $privilege): bool
    {
        if ($this->isAdmin()) {
            return true;
        }

        $privileges = $this->privileges ?? [];

        return in_array('*', $privileges, true) || in_array($privilege, $privileges, true);
    }

    /**
     * Branded reset mail instead of Notifiable's default, matching the LoginOtp pattern
     * rather than a second, differently-styled mail path.
     */
    public function sendPasswordResetNotification($token): void
    {
        $url = url(route('password.reset', ['token' => $token, 'email' => $this->email], false));

        Mail::to($this->email)->send(new ResetPassword($this, $url));
    }

    /**
     * Slugifies name (+ post), appending _2/_3/etc. on collision, checked against soft-deleted
     * rows too so a deleted user's username is not immediately reusable and confusing in the
     * audit log.
     */
    public static function uniqueUsername(string $name, ?string $post = null, ?int $exceptId = null): string
    {
        $base = substr(Str::slug(trim($name.' '.($post ?? '')), '_'), 0, 26) ?: 'user';
        $username = $base;
        $i = 2;

        while (
            static::withTrashed()->where('username', $username)
                ->when($exceptId, fn ($q) => $q->where('id', '!=', $exceptId))
                ->exists()
        ) {
            $username = "{$base}_{$i}";
            $i++;
        }

        return $username;
    }
}
