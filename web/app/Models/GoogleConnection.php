<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Attributes\Hidden;
use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\SoftDeletes;

#[Fillable(['user_id', 'google_sub', 'email', 'scopes', 'refresh_token', 'revoked_at'])]
#[Hidden(['refresh_token'])]
class GoogleConnection extends Model
{
    use HasUlids, SoftDeletes;

    protected function casts(): array
    {
        return [
            'scopes' => 'array',
            'refresh_token' => 'encrypted',
            'revoked_at' => 'datetime',
        ];
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function needsReconnect(): bool
    {
        return $this->revoked_at !== null;
    }
}
