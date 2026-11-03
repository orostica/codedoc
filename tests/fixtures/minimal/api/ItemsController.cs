using Microsoft.AspNetCore.Mvc;

namespace Demo;

[ApiController]
[Route("api/[controller]")]
public class ItemsController : ControllerBase
{
    [HttpGet]
    public IActionResult List()
    {
        return Ok(new[] { new { id = 1, name = "Example" } });
    }
}
