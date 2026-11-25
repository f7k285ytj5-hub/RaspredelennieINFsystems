using System.Drawing;
using System.Drawing.Imaging;
using System.Threading.Channels;
using System.Diagnostics;

namespace ImageRotationLab;

public sealed class MainForm : Form
{
    private readonly PictureBox _picture = new();
    private readonly Button _openButton = new() { Text = "Выбрать изображение", AutoSize = true };
    private readonly Button _startButton = new() { Text = "Начать обработку", AutoSize = true, Enabled = false };
    private readonly Button _cancelButton = new() { Text = "Отмена", AutoSize = true, Enabled = false };
    private readonly Button _saveButton = new() { Text = "Сохранить результат", AutoSize = true, Enabled = false };
    private readonly ComboBox _angleBox = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 100 };
    private readonly NumericUpDown _workersBox = new() { Minimum = 1, Maximum = 32, Value = Math.Clamp(Environment.ProcessorCount, 1, 32), Width = 65 };
    private readonly ProgressBar _progress = new() { Minimum = 0, Maximum = 100, Width = 260 };
    private readonly Label _status = new() { AutoSize = true, Text = "Выберите изображение." };

    private Bitmap? _sourceBitmap;
    private Bitmap? _resultBitmap;
    private CancellationTokenSource? _processingCts;

    // Создаёт окно, размещает элементы интерфейса и подключает обработчики
    // загрузки, запуска обработки, отмены, сохранения и закрытия формы.
    public MainForm()
    {
        Text = "Лабораторная работа №4 — многопоточная обработка изображений";
        Width = 1050;
        Height = 720;
        MinimumSize = new Size(800, 550);
        StartPosition = FormStartPosition.CenterScreen;

        _angleBox.Items.AddRange(new object[] { "90°", "180°", "270°" });
        _angleBox.SelectedIndex = 0;

        var controls = new FlowLayoutPanel
        {
            Dock = DockStyle.Top,
            AutoSize = true,
            Padding = new Padding(10),
            WrapContents = true
        };
        controls.Controls.AddRange(new Control[]
        {
            _openButton,
            new Label { Text = "Поворот:", AutoSize = true, Padding = new Padding(8, 8, 0, 0) },
            _angleBox,
            new Label { Text = "Потоков:", AutoSize = true, Padding = new Padding(8, 8, 0, 0) },
            _workersBox,
            _startButton,
            _cancelButton,
            _saveButton
        });

        _picture.Dock = DockStyle.Fill;
        _picture.SizeMode = PictureBoxSizeMode.Zoom;
        _picture.BackColor = Color.FromArgb(35, 35, 35);

        var bottom = new FlowLayoutPanel
        {
            Dock = DockStyle.Bottom,
            AutoSize = true,
            Padding = new Padding(10),
            WrapContents = true
        };
        bottom.Controls.Add(_progress);
        bottom.Controls.Add(_status);

        Controls.Add(_picture);
        Controls.Add(bottom);
        Controls.Add(controls);

        _openButton.Click += async (_, _) => await OpenImageAsync();
        _startButton.Click += async (_, _) => await StartProcessingAsync();
        _cancelButton.Click += (_, _) => _processingCts?.Cancel();
        _saveButton.Click += async (_, _) => await SaveResultAsync();
        FormClosing += (_, _) => _processingCts?.Cancel();
    }

    // Предлагает выбрать файл и асинхронно считывает его байты.
    // Декодирует изображение в фоновой задаче, заменяет исходное изображение
    // и обновляет предпросмотр; при ошибке выводит сообщение пользователю.
    private async Task OpenImageAsync()
    {
        using var dialog = new OpenFileDialog
        {
            Title = "Выберите изображение",
            Filter = "Изображения|*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff"
        };

        if (dialog.ShowDialog(this) != DialogResult.OK)
            return;

        try
        {
            SetBusy(true);
            _status.Text = "Асинхронное чтение изображения...";

            byte[] bytes = await File.ReadAllBytesAsync(dialog.FileName);

            // Декодирование Bitmap выполняется в фоновом потоке, чтобы не задерживать интерфейс.
            Bitmap loadedBitmap = await Task.Run(() =>
            {
                using var stream = new MemoryStream(bytes);
                using var decoded = new Bitmap(stream);
                return new Bitmap(decoded);
            });

            _sourceBitmap?.Dispose();
            _resultBitmap?.Dispose();
            _sourceBitmap = loadedBitmap;
            _resultBitmap = null;

            SetPreview(_sourceBitmap);
            _progress.Value = 0;
            _status.Text = $"Загружено: {_sourceBitmap.Width} × {_sourceBitmap.Height}";
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, $"Не удалось открыть изображение:\n{ex.Message}",
                "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
            _status.Text = "Ошибка загрузки.";
        }
        finally
        {
            SetBusy(false);
            _startButton.Enabled = _sourceBitmap is not null;
            _saveButton.Enabled = _resultBitmap is not null;
        }
    }

    // Запускает конвейер поворота: чтение пикселей, разбиение на тайлы,
    // передача заданий через канал и обработка заданным числом рабочих задач.
    // Координирует синхронизацию, прогресс и отмену, затем собирает результат
    // и выводит измеренное время после обновления предпросмотра.
    private async Task StartProcessingAsync()
    {
        if (_sourceBitmap is null)
            return;

        int angle = int.Parse(_angleBox.SelectedItem!.ToString()!.TrimEnd('°'));
        int workerCount = (int)_workersBox.Value;

        // Снимок исходного изображения не изменяется во время параллельной обработки.
        using var sourceCopy = new Bitmap(_sourceBitmap);
        int sourceWidth = sourceCopy.Width;
        int sourceHeight = sourceCopy.Height;

        _processingCts?.Dispose();
        _processingCts = new CancellationTokenSource();
        CancellationToken userToken = _processingCts.Token;

        SetBusy(true);
        _cancelButton.Enabled = true;
        _progress.Value = 0;
        _status.Text = "Подготовка изображения...";

        try
        {
            Stopwatch stopwatch = Stopwatch.StartNew();

            Color[] sourcePixels = await Task.Run(
                () => ReadPixels(sourceCopy, userToken), userToken);

            int outputWidth = angle == 180 ? sourceWidth : sourceHeight;
            int outputHeight = angle == 180 ? sourceHeight : sourceWidth;

            const int tileSize = 64;
            var tiles = new List<Tile>();
            for (int y = 0; y < sourceHeight; y += tileSize)
            for (int x = 0; x < sourceWidth; x += tileSize)
            {
                tiles.Add(new Tile(
                    x, y,
                    Math.Min(tileSize, sourceWidth - x),
                    Math.Min(tileSize, sourceHeight - y)));
            }

            var channel = Channel.CreateBounded<Tile>(
                new BoundedChannelOptions(Math.Max(2, workerCount * 2))
                {
                    FullMode = BoundedChannelFullMode.Wait,
                    SingleWriter = true,
                    SingleReader = false
                });

            var syncRoot = new object();
            var completedResults = new Queue<TileResult>();
            int completedTiles = 0;

            // Progress<T> создаётся в UI-потоке и возвращает обновления интерфейса в UI-контекст.
            IProgress<(int Percent, string Message)> progress =
                new Progress<(int Percent, string Message)>(value =>
                {
                    _progress.Value = Math.Clamp(value.Percent, 0, 100);
                    _status.Text = value.Message;
                });

            // SemaphoreSlim ограничивает число одновременно допущенных к обработке работников.
            using var semaphore = new SemaphoreSlim(workerCount, workerCount);

            // CountdownEvent сигнализирует, что обработаны все фрагменты изображения.
            using var allTilesCompleted = new CountdownEvent(tiles.Count);

            // Внутренний токен останавливает весь конвейер, если один из этапов завершился ошибкой.
            using var pipelineCts = CancellationTokenSource.CreateLinkedTokenSource(userToken);
            CancellationToken pipelineToken = pipelineCts.Token;

            _status.Text = $"Обработка: 0 / {tiles.Count} фрагментов";

            Task producer = Task.Run(async () =>
            {
                try
                {
                    foreach (Tile tile in tiles)
                    {
                        pipelineToken.ThrowIfCancellationRequested();
                        await channel.Writer.WriteAsync(tile, pipelineToken);
                    }
                }
                catch
                {
                    pipelineCts.Cancel();
                    throw;
                }
                finally
                {
                    channel.Writer.TryComplete();
                }
            });

            Task[] workers = Enumerable.Range(0, workerCount).Select(_ => Task.Run(async () =>
            {
                try
                {
                    await foreach (Tile tile in channel.Reader.ReadAllAsync(pipelineToken))
                    {
                        await semaphore.WaitAsync(pipelineToken);
                        try
                        {
                            TileResult result = ProcessTile(
                                tile, sourcePixels, sourceWidth, sourceHeight,
                                outputWidth, angle, pipelineToken);

                            int done;
                            lock (syncRoot)
                            {
                                completedResults.Enqueue(result);
                                done = ++completedTiles;
                            }

                            progress.Report((
                                (int)(done * 100.0 / tiles.Count),
                                $"Обработка: {done} / {tiles.Count} фрагментов"));

                            // Каждый работник сигнализирует о завершении своего фрагмента.
                            allTilesCompleted.Signal();
                        }
                        finally
                        {
                            semaphore.Release();
                        }
                    }
                }
                catch
                {
                    pipelineCts.Cancel();
                    throw;
                }
            })).ToArray();

            // Ожидание CountdownEvent вынесено в отдельную задачу, чтобы не блокировать UI.
            Task allTilesSignalTask = Task.Run(() => allTilesCompleted.Wait(pipelineToken));

            await Task.WhenAll(workers.Append(producer).Append(allTilesSignalTask));

            pipelineToken.ThrowIfCancellationRequested();

            // Чтение общей очереди результатов также выполняется под той же критической секцией.
            TileResult[] results;
            int finalCompletedCount;
            lock (syncRoot)
            {
                results = completedResults.ToArray();
                completedResults.Clear();
                finalCompletedCount = completedTiles;
            }

            Color[] outputPixels = new Color[outputWidth * outputHeight];
            foreach (TileResult result in results)
            {
                foreach (PixelValue pixel in result.Pixels)
                    outputPixels[pixel.Index] = pixel.Color;
            }

            Bitmap newResult = await Task.Run(
                () => CreateBitmap(outputPixels, outputWidth, outputHeight),
                pipelineToken);

            pipelineToken.ThrowIfCancellationRequested();

            _resultBitmap?.Dispose();
            _resultBitmap = newResult;
            SetPreview(_resultBitmap);

            _saveButton.Enabled = true;
            _progress.Value = 100;
            _status.Text =
    $"Готово! Фрагментов: {finalCompletedCount}. " +
    $"Время: {stopwatch.Elapsed.TotalMilliseconds:F2} мс";
        }
        catch (OperationCanceledException)
        {
            _resultBitmap?.Dispose();
            _resultBitmap = null;
            _saveButton.Enabled = false;
            _progress.Value = 0;
            _status.Text = "Обработка отменена. Частичный результат не сохранён.";
        }
        catch (Exception ex)
        {
            _resultBitmap?.Dispose();
            _resultBitmap = null;
            _saveButton.Enabled = false;
            _status.Text = "Ошибка обработки.";
            MessageBox.Show(this, $"Ошибка обработки:\n{ex.Message}",
                "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            _processingCts?.Dispose();
            _processingCts = null;
            SetBusy(false);
            _startButton.Enabled = _sourceBitmap is not null;
            _cancelButton.Enabled = false;
        }
    }

    // Предлагает выбрать путь и кодирует готовое изображение в PNG в фоне.
    // Асинхронно записывает данные во временный файл, затем заменяет целевой.
    // При ошибке сообщает о ней и пытается удалить временный файл.
    private async Task SaveResultAsync()
    {
        if (_resultBitmap is null)
            return;

        using var dialog = new SaveFileDialog
        {
            Title = "Сохранить результат",
            Filter = "PNG изображение|*.png",
            DefaultExt = "png",
            FileName = "rotated-image.png"
        };

        if (dialog.ShowDialog(this) != DialogResult.OK)
            return;

        string? temporaryPath = null;

        try
        {
            SetBusy(true);
            _status.Text = "Подготовка PNG...";

            // Кодирование изображения выполняется вне UI-потока.
            byte[] pngBytes = await Task.Run(() =>
            {
                using var memory = new MemoryStream();
                _resultBitmap.Save(memory, ImageFormat.Png);
                return memory.ToArray();
            });

            string targetPath = dialog.FileName;
            temporaryPath = targetPath + "." + Guid.NewGuid().ToString("N") + ".tmp";

            _status.Text = "Асинхронная запись файла...";
            await using (var file = new FileStream(
                temporaryPath, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                bufferSize: 81920, options: FileOptions.Asynchronous))
            {
                await file.WriteAsync(pngBytes);
                await file.FlushAsync();
            }

            // Готовый временный файл атомарно переносится на целевой путь.
            File.Move(temporaryPath, targetPath, overwrite: true);
            temporaryPath = null;
            _status.Text = "Результат сохранён.";
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, $"Не удалось сохранить изображение:\n{ex.Message}",
                "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
            _status.Text = "Ошибка сохранения.";
        }
        finally
        {
            if (temporaryPath is not null)
            {
                try
                {
                    if (File.Exists(temporaryPath))
                        File.Delete(temporaryPath);
                }
                catch
                {
                    // Ошибка очистки временного файла не должна скрывать исходную ошибку.
                }
            }

            SetBusy(false);
            _startButton.Enabled = _sourceBitmap is not null;
            _saveButton.Enabled = _resultBitmap is not null;
        }
    }

    // Считывает цвета изображения в массив: индекс пикселя равен y * width + x.
    // Проверяет отмену перед каждой строкой; вызывается из фоновой задачи.
    private static Color[] ReadPixels(Bitmap bitmap, CancellationToken token)
    {
        var pixels = new Color[bitmap.Width * bitmap.Height];

        for (int y = 0; y < bitmap.Height; y++)
        {
            token.ThrowIfCancellationRequested();

            for (int x = 0; x < bitmap.Width; x++)
                pixels[y * bitmap.Width + x] = bitmap.GetPixel(x, y);
        }

        return pixels;
    }

    // Обрабатывает один тайл: вычисляет новые координаты пикселей при повороте
    // на 90, 180 или 270 градусов по часовой стрелке и сохраняет цвет и индекс.
    // Возвращает отдельный результат фрагмента, не изменяя исходный массив;
    // проверяет отмену перед обработкой каждой строки.
    private static TileResult ProcessTile(
        Tile tile, Color[] source, int sourceWidth, int sourceHeight,
        int outputWidth, int angle, CancellationToken token)
    {
        var values = new List<PixelValue>(tile.Width * tile.Height);

        for (int y = tile.Y; y < tile.Y + tile.Height; y++)
        {
            token.ThrowIfCancellationRequested();

            for (int x = tile.X; x < tile.X + tile.Width; x++)
            {
                int dx, dy;

                switch (angle)
                {
                    case 90:
                        dx = sourceHeight - 1 - y;
                        dy = x;
                        break;
                    case 180:
                        dx = sourceWidth - 1 - x;
                        dy = sourceHeight - 1 - y;
                        break;
                    case 270:
                        dx = y;
                        dy = sourceWidth - 1 - x;
                        break;
                    default:
                        throw new InvalidOperationException("Неподдерживаемый угол поворота.");
                }

                int destinationIndex = dy * outputWidth + dx;
                values.Add(new PixelValue(destinationIndex, source[y * sourceWidth + x]));
            }
        }

        return new TileResult(values.ToArray());
    }

    // Создаёт Bitmap формата 32bppArgb из собранного массива цветов.
    // При ошибке заполнения освобождает созданное изображение и передаёт
    // исключение вызывающему коду. При успехе освобождением управляет вызывающий код.
    private static Bitmap CreateBitmap(Color[] pixels, int width, int height)
    {
        var bitmap = new Bitmap(width, height, PixelFormat.Format32bppArgb);

        try
        {
            for (int y = 0; y < height; y++)
            for (int x = 0; x < width; x++)
                bitmap.SetPixel(x, y, pixels[y * width + x]);

            return bitmap;
        }
        catch
        {
            bitmap.Dispose();
            throw;
        }
    }

    // Показывает отдельную копию изображения в PictureBox и освобождает
    // предыдущий предпросмотр. Вызывается в потоке пользовательского интерфейса.
    private void SetPreview(Bitmap bitmap)
    {
        Image? oldImage = _picture.Image;
        _picture.Image = new Bitmap(bitmap);
        oldImage?.Dispose();
    }

    // Переключает доступность загрузки, настроек, запуска и сохранения.
    // Во время операции блокирует эти элементы; после неё учитывает наличие
    // исходного изображения и результата. Кнопка отмены управляется отдельно.
    private void SetBusy(bool busy)
    {
        _openButton.Enabled = !busy;
        _angleBox.Enabled = !busy;
        _workersBox.Enabled = !busy;
        _startButton.Enabled = !busy && _sourceBitmap is not null;
        _saveButton.Enabled = !busy && _resultBitmap is not null;
    }

    // При освобождении формы запрашивает отмену обработки и освобождает
    // источник отмены, исходное изображение, результат и копию предпросмотра.
    // Затем передаёт освобождение остальных ресурсов базовому классу Form.
    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _processingCts?.Cancel();
            _processingCts?.Dispose();
            _sourceBitmap?.Dispose();
            _resultBitmap?.Dispose();
            _picture.Image?.Dispose();
        }

        base.Dispose(disposing);
    }

    private sealed record Tile(int X, int Y, int Width, int Height);
    private sealed record PixelValue(int Index, Color Color);
    private sealed record TileResult(PixelValue[] Pixels);
}
