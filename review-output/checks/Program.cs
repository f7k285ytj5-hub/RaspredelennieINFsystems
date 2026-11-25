using System.Drawing;
using System.Reflection;
using ImageRotationLab;

var flags = BindingFlags.NonPublic | BindingFlags.Static;
var form = typeof(MainForm);
var read = form.GetMethod("ReadPixels", flags)!;
var process = form.GetMethod("ProcessTile", flags)!;
var create = form.GetMethod("CreateBitmap", flags)!;
var tileType = form.GetNestedType("Tile", BindingFlags.NonPublic)!;
int tests = 0;
foreach (var (width, height) in new[] { (1,1), (1,65), (65,1), (3,2), (64,64), (65,67), (129,130) })
foreach (int angle in new[] { 90, 180, 270 })
foreach (int workers in new[] { 1, 2, 4, 8 })
{
    using var source = new Bitmap(width, height);
    for (int y = 0; y < height; y++)
    for (int x = 0; x < width; x++)
        source.SetPixel(x, y, Color.FromArgb(255, x % 256, y % 256, (x*7+y*13) % 256));
    var colors = (Color[])read.Invoke(null, new object[] { source, CancellationToken.None })!;
    int ow = angle == 180 ? width : height;
    int oh = angle == 180 ? height : width;
    var tiles = new List<object>();
    for (int y = 0; y < height; y += 64)
    for (int x = 0; x < width; x += 64)
        tiles.Add(Activator.CreateInstance(tileType, x, y, Math.Min(64,width-x), Math.Min(64,height-y))!);
    var results = new System.Collections.Concurrent.ConcurrentBag<object>();
    Parallel.ForEach(tiles, new ParallelOptions { MaxDegreeOfParallelism = workers }, tile =>
        results.Add(process.Invoke(null, new object[] {tile, colors, width, height, ow, angle, CancellationToken.None})!));
    var output = new Color[ow*oh];
    var counts = new int[output.Length];
    foreach (var result in results)
    foreach (var pixel in (Array)result.GetType().GetProperty("Pixels")!.GetValue(result)!)
    {
        int index = (int)pixel.GetType().GetProperty("Index")!.GetValue(pixel)!;
        output[index] = (Color)pixel.GetType().GetProperty("Color")!.GetValue(pixel)!;
        counts[index]++;
    }
    if (counts.Any(c => c != 1)) throw new Exception("Duplicate or missing pixel");
    using var actual = (Bitmap)create.Invoke(null, new object[] {output, ow, oh})!;
    using var expected = new Bitmap(source);
    expected.RotateFlip(angle switch { 90 => RotateFlipType.Rotate90FlipNone, 180 => RotateFlipType.Rotate180FlipNone, _ => RotateFlipType.Rotate270FlipNone });
    for (int y = 0; y < oh; y++)
    for (int x = 0; x < ow; x++)
        if (actual.GetPixel(x,y).ToArgb() != expected.GetPixel(x,y).ToArgb())
            throw new Exception($"Mismatch {width}x{height}, angle={angle}, workers={workers}, ({x},{y})");
    tests++;
}
Console.WriteLine($"PASS: {tests} pixel comparisons with RotateFlip; all destination pixels written exactly once.");
using var cts = new CancellationTokenSource();
cts.Cancel();
try
{
    var tile = Activator.CreateInstance(tileType, 0, 0, 1, 1)!;
    process.Invoke(null, new object[] { tile, new[] {Color.Red}, 1, 1, 1, 90, cts.Token });
    throw new Exception("Cancellation not observed");
}
catch (TargetInvocationException ex) when (ex.InnerException is OperationCanceledException)
{
    Console.WriteLine("PASS: ProcessTile observes cancellation.");
}
Console.WriteLine("Scope: actual pixel methods only; GUI lifecycle and full Channel pipeline not exercised.");
