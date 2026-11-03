using Microsoft.AspNetCore.Mvc;
using System.Text.Json;

namespace Demo;

[ApiController]
[Route("api/people")]
public class PeopleController : ControllerBase
{
    [HttpPost]
    public IActionResult Create([FromBody] JsonElement body)
    {
        if (!body.TryGetProperty("name", out var name))
        {
            return BadRequest();
        }
        return Ok();
    }
}
