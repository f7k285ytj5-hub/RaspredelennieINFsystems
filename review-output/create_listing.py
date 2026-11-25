from pathlib import Path
import textwrap
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

root = Path(__file__).resolve().parent.parent
source = (root / 'projectRIS/ImageRotationLab/ImageRotationLab/MainForm.cs').read_text(encoding='utf-8')
def extract(start, end):
    return textwrap.dedent(source[source.index(start):source.index(end, source.index(start))]).strip()

parts = []
parts.append(('Асинхронное чтение изображения', '''// Фрагмент OpenImageAsync после выбора файла.
// Чтение файла не блокирует поток интерфейса.
byte[] bytes = await File.ReadAllBytesAsync(dialog.FileName);

// Декодирование вынесено в штатный пул потоков.
Bitmap loadedBitmap = await Task.Run(() =>
{
    using var stream = new MemoryStream(bytes);
    using var decoded = new Bitmap(stream);
    // Копия изображения используется после закрытия потока.
    return new Bitmap(decoded);
});

// Освобождаем предыдущие изображения и показываем новое.
_sourceBitmap?.Dispose();
_resultBitmap?.Dispose();
_sourceBitmap = loadedBitmap;
_resultBitmap = null;
SetPreview(_sourceBitmap);'''))

parts.append(('Подготовка фрагментов и очереди заданий', '''// Фрагменты StartProcessingAsync.
// Число работников берётся из поля «Потоков».
int workerCount = (int)_workersBox.Value;

// Источник отмены связан с кнопкой «Отмена».
_processingCts?.Dispose();
_processingCts = new CancellationTokenSource();
CancellationToken userToken = _processingCts.Token;

// Замер начинается перед чтением пикселей.
Stopwatch stopwatch = Stopwatch.StartNew();
Color[] sourcePixels = await Task.Run(
    () => ReadPixels(sourceCopy, userToken), userToken);

// При повороте на 90° и 270° размеры меняются местами.
int outputWidth = angle == 180 ? sourceWidth : sourceHeight;
int outputHeight = angle == 180 ? sourceHeight : sourceWidth;

// Крайние фрагменты могут иметь размер меньше 64 × 64.
''' + extract('            const int tileSize = 64;', '            var syncRoot = new object();').replace('var channel =', '// Заполненная очередь приостанавливает производителя.\nvar channel =')))

parts.append(('Общие данные и механизмы синхронизации', '''// Фрагмент StartProcessingAsync.
// Очередь результатов и счётчик защищаются одним lock.
var syncRoot = new object();
var completedResults = new Queue<TileResult>();
int completedTiles = 0;

// Уведомления доставляются в контекст UI-потока.
IProgress<(int Percent, string Message)> progress =
    new Progress<(int Percent, string Message)>(value =>
    {
        _progress.Value = Math.Clamp(value.Percent, 0, 100);
        _status.Text = value.Message;
    });

// Число разрешений равно количеству рабочих задач.
using var semaphore = new SemaphoreSlim(workerCount, workerCount);

// По одному сигналу на каждый обработанный фрагмент.
using var allTilesCompleted = new CountdownEvent(tiles.Count);

// Пользовательская отмена передаётся всему конвейеру.
// При ошибке этапа этот же источник отменяется из catch.
using var pipelineCts =
    CancellationTokenSource.CreateLinkedTokenSource(userToken);
CancellationToken pipelineToken = pipelineCts.Token;

// Обработчик кнопки из конструктора MainForm.
_cancelButton.Click += (_, _) => _processingCts?.Cancel();'''))

producer = extract('            Task producer = Task.Run(async () =>', '            Task[] workers =')
producer = producer.replace('await channel.Writer.WriteAsync(tile, pipelineToken);', '// Ожидание места в канале поддерживает отмену.\n            await channel.Writer.WriteAsync(tile, pipelineToken);')
producer = producer.replace('pipelineCts.Cancel();', '// Ошибка производителя останавливает работников.\n        pipelineCts.Cancel();')
producer = producer.replace('channel.Writer.TryComplete();', '// Новых заданий больше не будет.\n        channel.Writer.TryComplete();')
parts.append(('Производитель заданий', '// Фрагмент StartProcessingAsync.\n' + producer))

workers = extract('            Task[] workers =', '            // Ожидание CountdownEvent')
workers = workers.replace('Task[] workers = Enumerable.Range(0, workerCount).Select(_ => Task.Run(async () =>', 'Task[] workers = Enumerable.Range(0, workerCount)\n    .Select(_ => Task.Run(async () =>')
workers = workers.replace('await foreach (Tile tile in channel.Reader.ReadAllAsync(pipelineToken))', 'await foreach (Tile tile in\n            channel.Reader.ReadAllAsync(pipelineToken))')
workers = workers.replace('await semaphore.WaitAsync(pipelineToken);', '// Разрешение получено до начала обработки.\n            await semaphore.WaitAsync(pipelineToken);')
workers = workers.replace('lock (syncRoot)', '// Критическая секция защищает общие данные.\n                lock (syncRoot)')
workers = workers.replace('semaphore.Release();', '// Разрешение возвращается и при исключении.\n                semaphore.Release();')
parts.append(('Рабочие задачи и критическая секция', '// Фрагмент StartProcessingAsync.\n' + workers))

assembly = extract('            // Ожидание CountdownEvent', '            _saveButton.Enabled = true;')
assembly = assembly.replace('// Ожидание CountdownEvent вынесено в отдельную задачу, чтобы не блокировать UI.', '// Ожидание события выполняется вне потока интерфейса.')
assembly = assembly.replace('Task allTilesSignalTask = Task.Run(() => allTilesCompleted.Wait(pipelineToken));', 'Task allTilesSignalTask = Task.Run(\n    () => allTilesCompleted.Wait(pipelineToken));')
assembly = assembly.replace('await Task.WhenAll(workers.Append(producer).Append(allTilesSignalTask));', '// Дожидаемся работников, производителя и ожидания события.\nawait Task.WhenAll(\n    workers.Append(producer).Append(allTilesSignalTask));')
assembly = assembly.replace('// Чтение общей очереди результатов также выполняется под той же критической секцией.', '// Извлекаем результаты под той же блокировкой.')
assembly += '\n\n// В текущем коде время считывается после SetPreview.\n_status.Text =\n    $"Готово! Фрагментов: {finalCompletedCount}. " +\n    $"Время: {stopwatch.Elapsed.TotalMilliseconds:F2} мс";'
parts.append(('Ожидание завершения и сборка результата', '// Фрагмент StartProcessingAsync.\n' + assembly))

cancel_start = source.index('        catch (OperationCanceledException)')
cancel_end = source.index('    private async Task SaveResultAsync()', cancel_start)
cancel = source[cancel_start:cancel_end].rstrip().rsplit('\n', 1)[0]
cancel = textwrap.dedent(cancel).strip()
cancel = cancel.replace('_resultBitmap?.Dispose();', '// Отменённый или ошибочный результат недоступен.\n    _resultBitmap?.Dispose();')
parts.append(('Обработка отмены и ошибок', '// Блоки catch и finally метода StartProcessingAsync.\n' + cancel))

process = extract('    private static TileResult ProcessTile(', '    private static Bitmap CreateBitmap(')
process = process.replace('token.ThrowIfCancellationRequested();', '// Проверяем отмену перед каждой строкой.\n        token.ThrowIfCancellationRequested();')
process = process.replace('case 90:', '// Поворот по часовой стрелке.\n                case 90:')
process = process.replace('throw new InvalidOperationException("Неподдерживаемый угол поворота.");', 'throw new InvalidOperationException(\n                        "Неподдерживаемый угол поворота.");')
process = process.replace('values.Add(new PixelValue(destinationIndex, source[y * sourceWidth + x]));', 'values.Add(new PixelValue(\n                destinationIndex, source[y * sourceWidth + x]));')
parts.append(('Перестановка пикселей при повороте', process))

save_start = source.index('            // Кодирование изображения выполняется вне UI-потока.')
save_end = source.index('        catch (Exception ex)', save_start)
save = source[save_start:save_end].rstrip().rsplit('\n', 1)[0]
save = textwrap.dedent(save).strip()
save = save.replace('temporaryPath = targetPath + "." + Guid.NewGuid().ToString("N") + ".tmp";', 'temporaryPath = targetPath + "." +\n    Guid.NewGuid().ToString("N") + ".tmp";')
save = save.replace('// Готовый временный файл атомарно переносится на целевой путь.', '// После завершения записи заменяем целевой файл.')
parts.append(('Асинхронное сохранение результата', '// Фрагмент SaveResultAsync после выбора пути сохранения.\n' + save.strip() + '''

// Фрагмент finally: удаление временного файла при ошибке.
if (temporaryPath is not null)
{
    try
    {
        if (File.Exists(temporaryPath))
            File.Delete(temporaryPath);
    }
    catch
    {
        // Ошибка очистки не скрывает исходную ошибку записи.
    }
}'''))

doc = Document()
s = doc.sections[0]
s.page_width, s.page_height = Cm(21), Cm(29.7)
s.left_margin, s.right_margin = Cm(2.5), Cm(1.5)
s.top_margin = s.bottom_margin = Cm(1.8)
for name in ['Normal', 'Title', 'Heading 1']:
    style = doc.styles[name]
    style.font.name = 'Times New Roman'
    style.font.size = Pt(14)
    style.font.color.rgb = RGBColor(0,0,0)
    for attr in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
        style.element.get_or_add_rPr().rFonts.set(qn('w:' + attr), 'Times New Roman')
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.space_before = Pt(0)
doc.add_paragraph('Основные фрагменты программы MainForm.cs', 'Title')
doc.add_paragraph('Листинг соответствует текущей реализации. Приведены отдельные фрагменты с поясняющими комментариями; настройка интерфейса и часть служебных операций опущены. Фрагменты не являются самостоятельной программой.')

for index, (title, code) in enumerate(parts):
    if index:
        doc.add_page_break()
    doc.add_paragraph(title, 'Heading 1')
    for line in code.splitlines():
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = Pt(12)
        p.paragraph_format.widow_control = False
        run = p.add_run(line)
        run.font.name = 'Consolas'
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0,0,0)
        run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), 'Consolas')

out = root / 'Листинг программы с комментариями.docx'
for element in (doc.element, doc.styles.element):
    for border in list(element.iter(qn('w:pBdr'))):
        border.getparent().remove(border)
doc.save(out)
(root / 'Листинг программы с комментариями.txt').write_text('\n\n'.join(title+'\n\n'+code for title,code in parts),encoding='utf-8')
for title,code in parts:
    print(len(code.splitlines()), max(map(len,code.splitlines())), title)
print(out)
