<?php

namespace App\Mail;

use App\Models\User;
use Illuminate\Bus\Queueable;
use Illuminate\Mail\Mailable;
use Illuminate\Queue\SerializesModels;

class ResetPassword extends Mailable
{
    use Queueable, SerializesModels;

    public function __construct(public User $user, public string $url) {}

    public function build(): self
    {
        return $this->subject('Reset your password')
            ->view('emails.reset-password')
            ->with(['user' => $this->user, 'url' => $this->url]);
    }
}
