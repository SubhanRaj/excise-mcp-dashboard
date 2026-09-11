<?php

namespace Tests\Feature;

use Tests\TestCase;

class ErrorPagesTest extends TestCase
{
    public function test_an_unknown_path_renders_the_custom_404_page(): void
    {
        $response = $this->get('/no-such-path');

        $response->assertNotFound();
        $response->assertSee('404');
        $response->assertSee('does not exist', false);
        $response->assertSee(config('app.name'), false);
    }
}
