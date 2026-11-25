from pathlib import Path
import re
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml.ns import qn

root = Path(__file__).resolve().parent.parent
src = Path(r'C:\Users\apani\.codex\attachments\c8658cd8-b0eb-442b-9f95-4322a9da078a\Вставленный текст.txt').read_text(encoding='utf-8-sig')
src = src.replace('\r\n','\n')

def replace_region(start, end, replacement):
    global src
    a = src.index(start)
    b = src.index(end, a)
    src = src[:a] + replacement + src[b:]

# Preserve the original class and method order; omissions are explicit.
replace_region('    private readonly PictureBox', '    private Bitmap?',
    '    // Объявления элементов интерфейса опущены.\n')
replace_region('        Text = "Лабораторная работа', '        _openButton.Click',
    '        // Настройка окна и размещение элементов опущены.\n'
    '        // Кнопки запускают чтение, обработку, отмену и запись.\n')

replace_region('        using var dialog = new OpenFileDialog', '        if (dialog.ShowDialog',
    '        // Выбор исходного изображения.\n'
    '        using var dialog = new OpenFileDialog();\n'
    '        // Заголовок и фильтр форматов опущены.\n')
replace_region('        using var dialog = new SaveFileDialog', '        if (dialog.ShowDialog',
    '        using var dialog = new SaveFileDialog();\n'
    '        // Настройки диалога сохранения PNG опущены.\n')

# Remove auxiliary UI messages and button updates, retaining progress and timing.
src = re.sub(r'^\s*_status\.Text = "(?:Асинхронное чтение изображения\.\.\.|Подготовка изображения\.\.\.|Подготовка PNG\.\.\.|Асинхронная запись файла\.\.\.|Результат сохранён\.|Ошибка загрузки\.|Ошибка сохранения\.)";\n', '\n', src, flags=re.M)
src = re.sub(r'^\s*_status\.Text = \$"(?:Загружено:|Обработка: 0)[^\n]*\n', '\n', src, flags=re.M)
src = re.sub(r'^\s*MessageBox\.Show\(this,[^\n]*\n\s*"Ошибка", MessageBoxButtons\.OK, MessageBoxIcon\.Error\);', '\n            // Сообщение об ошибке выводится пользователю (опущено).', src, flags=re.M)
src = src.replace('catch (Exception ex)', 'catch (Exception)')

# Use short comments at the meaningful synchronization and I/O points.
comments = {
    '// Декодирование Bitmap выполняется в фоновом потоке, чтобы не задерживать интерфейс.': '// Декодирование выполняется в пуле потоков.',
    '// Снимок исходного изображения не изменяется во время параллельной обработки.': '// Работники читают неизменяемый снимок изображения.',
    '// Progress<T> создаётся в UI-потоке и возвращает обновления интерфейса в UI-контекст.': '// Обновление прогресса передаётся в UI-поток.',
    '// SemaphoreSlim ограничивает число одновременно допущенных к обработке работников.': '// Число разрешений равно числу рабочих задач.',
    '// CountdownEvent сигнализирует, что обработаны все фрагменты изображения.': '// Счётчик завершения: один сигнал на фрагмент.',
    '// Внутренний токен останавливает весь конвейер, если один из этапов завершился ошибкой.': '// Общая отмена при нажатии кнопки или ошибке этапа.',
    '// Каждый работник сигнализирует о завершении своего фрагмента.': '// Уменьшаем число оставшихся фрагментов.',
    '// Ожидание CountdownEvent вынесено в отдельную задачу, чтобы не блокировать UI.': '// Ожидание события вынесено из UI-потока.',
    '// Чтение общей очереди результатов также выполняется под той же критической секцией.': '// Извлечение результатов защищено тем же lock.',
    '// Готовый временный файл атомарно переносится на целевой путь.': '// Целевой файл заменяется после завершения записи.',
    '// Ошибка очистки временного файла не должна скрывать исходную ошибку.': '// Ошибка очистки не скрывает ошибку записи.'
}
for a,b in comments.items(): src = src.replace(a,b)
src = src.replace('            byte[] bytes = await File.ReadAllBytesAsync', '            // Асинхронное чтение файла.\n            byte[] bytes = await File.ReadAllBytesAsync')
src = src.replace('            const int tileSize = 64;', '            // Деление на тайлы; крайние тайлы могут быть меньше.\n            const int tileSize = 64;')
src = src.replace('            var channel = Channel.CreateBounded<Tile>(', '            // При заполнении канала производитель ожидает.\n            var channel = Channel.CreateBounded<Tile>(')
src = src.replace('            Task producer =', '            // Производитель помещает задания в общую очередь.\n            Task producer =')
src = src.replace('                    channel.Writer.TryComplete();', '                    // Закрытие записи позволяет завершить чтение.\n                    channel.Writer.TryComplete();')
src = src.replace('            Task[] workers = Enumerable.Range(0, workerCount).Select(_ => Task.Run(async () =>', '            // Фиксированное число обработчиков на штатном пуле .NET.\n            Task[] workers = Enumerable.Range(0, workerCount)\n                .Select(_ => Task.Run(async () =>')
src = src.replace('                            lock (syncRoot)', '                            // Общая очередь и счётчик изменяются под lock.\n                            lock (syncRoot)')
src = src.replace('                            semaphore.Release();', '                            // Разрешение возвращается и при ошибке.\n                            semaphore.Release();')
src = src.replace('            await Task.WhenAll(workers.Append(producer).Append(allTilesSignalTask));', '            // Ждём завершения всех участников конвейера.\n            await Task.WhenAll(\n                workers.Append(producer).Append(allTilesSignalTask));')
src = src.replace('            Task allTilesSignalTask = Task.Run(() => allTilesCompleted.Wait(pipelineToken));', '            Task allTilesSignalTask = Task.Run(\n                () => allTilesCompleted.Wait(pipelineToken));')
src = src.replace('            using var pipelineCts = CancellationTokenSource.CreateLinkedTokenSource(userToken);', '            using var pipelineCts =\n                CancellationTokenSource.CreateLinkedTokenSource(userToken);')
src = src.replace('                    await foreach (Tile tile in channel.Reader.ReadAllAsync(pipelineToken))', '                    await foreach (Tile tile in\n                        channel.Reader.ReadAllAsync(pipelineToken))')
src = src.replace('            Color[] outputPixels =', '            // Сборка начинается после завершения работников.\n            Color[] outputPixels =')
src = src.replace('        catch (OperationCanceledException)', '        // После отмены сохранение результата запрещено.\n        catch (OperationCanceledException)')
src = src.replace('            Stopwatch stopwatch = Stopwatch.StartNew();', '            // Замер включает чтение пикселей и сборку результата.\n            Stopwatch stopwatch = Stopwatch.StartNew();')
src = src.replace('    $"Готово!', '                $"Готово!').replace('    $"Время:', '                $"Время:')
src = src.replace('        var pixels = new Color[bitmap.Width * bitmap.Height];', '        // Пиксель (x, y) хранится по индексу y * width + x.\n        var pixels = new Color[bitmap.Width * bitmap.Height];')
src = src.replace('                switch (angle)', '                // Новые координаты пикселя при повороте.\n                switch (angle)')
src = src.replace('                        throw new InvalidOperationException("Неподдерживаемый угол поворота.");', '                        throw new InvalidOperationException(\n                            "Неподдерживаемый угол поворота.");')
src = src.replace('                values.Add(new PixelValue(destinationIndex, source[y * sourceWidth + x]));', '                values.Add(new PixelValue(\n                    destinationIndex, source[y * sourceWidth + x]));')
src = src.replace('            temporaryPath = targetPath + "." + Guid.NewGuid().ToString("N") + ".tmp";', '            temporaryPath = targetPath + "." +\n                Guid.NewGuid().ToString("N") + ".tmp";')

# Keep helper signatures in their original places, but omit UI-only bodies.
replace_region('    private void SetPreview(Bitmap bitmap)', '    protected override void Dispose',
    '    private void SetPreview(Bitmap bitmap)\n    {\n'
    '        // Копирование изображения в PictureBox и освобождение\n'
    '        // предыдущего предпросмотра опущены.\n    }\n\n'
    '    private void SetBusy(bool busy)\n    {\n'
    '        // Переключение доступности элементов интерфейса опущено.\n    }\n\n')
src = src.replace('    protected override void Dispose(bool disposing)', '    // Освобождение изображений и источника отмены.\n    protected override void Dispose(bool disposing)')
src = src.replace('    private sealed record Tile(', '    // Описание тайла, пикселя результата и обработанного фрагмента.\n    private sealed record Tile(')

# Omit repetitive presentation state; retain the progress callback, final
# measurement, and explicit disabling of saving on cancellation/error.
src = re.sub(r'^\s*_(?:startButton|cancelButton)\.Enabled = [^\n]+;\n', '\n', src, flags=re.M)
src = re.sub(r'^\s*_saveButton\.Enabled = _resultBitmap is not null;\n', '\n', src, flags=re.M)
src = re.sub(r'^\s*_progress\.Value = 0;\n', '\n', src, flags=re.M)
src = src.replace('                        dx = sourceHeight - 1 - y;\n                        dy = x;', '                        dx = sourceHeight - 1 - y; dy = x;')
src = src.replace('                        dx = sourceWidth - 1 - x;\n                        dy = sourceHeight - 1 - y;', '                        dx = sourceWidth - 1 - x; dy = sourceHeight - 1 - y;')
src = src.replace('                        dx = y;\n                        dy = sourceWidth - 1 - x;', '                        dx = y; dy = sourceWidth - 1 - x;')
src = src.replace('                catch\n                {\n                    pipelineCts.Cancel();\n                    throw;\n                }', '                catch { pipelineCts.Cancel(); throw; }')
src = src.replace('        catch\n        {\n            bitmap.Dispose();\n            throw;\n        }', '        catch { bitmap.Dispose(); throw; }')
src = src.replace('        catch (Exception)\n        {\n            // Сообщение об ошибке выводится пользователю (опущено).\n        }', '        catch (Exception) { /* Вывод сообщения об ошибке опущен. */ }')

# Compact single-statement blocks without changing nesting or operation order.
pattern = re.compile(r'^( +)([^\n{}]+)\n\1\{\n\1    ([^\n{}]+;)\n\1\}', re.M)
def compact(match):
    result = match[1] + match[2] + ' { ' + match[3] + ' }'
    return result if len(result) <= 84 else match[0]
src = pattern.sub(compact, src)

# Keep blank lines only between method definitions to shorten the report.
lines = src.splitlines()
lines = [line for i,line in enumerate(lines) if line.strip() or (i+1<len(lines) and re.match(r'    (private (?:async|static|void)|public MainForm|protected override)', lines[i+1]))]
src = '\n'.join(lines).strip()+'\n'
src = pattern.sub(compact, src)
src = src.replace('        catch (Exception)\n        {\n            // Сообщение об ошибке выводится пользователю (опущено).\n        }', '        catch (Exception) { /* Вывод сообщения об ошибке опущен. */ }')
out_txt = root / 'Сокращённый листинг MainForm.txt'
out_txt.write_text(src,encoding='utf-8')

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin, sec.right_margin = Cm(2), Cm(1)
sec.top_margin = sec.bottom_margin = Cm(1.7)
style = doc.styles['Normal']
style.font.name = 'Times New Roman'
style.font.size = Pt(14)
style.font.color.rgb = RGBColor(0,0,0)
style.paragraph_format.space_after = Pt(0)
p = doc.add_paragraph('Сокращённый листинг MainForm.cs')
p.runs[0].bold = True
p = doc.add_paragraph('Сохранены класс и порядок методов. Пропуски вспомогательного кода обозначены комментариями. Листинг предназначен для отчёта.')
p.paragraph_format.space_after = Pt(8)
for line in src.splitlines():
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = Pt(11)
    p.paragraph_format.widow_control = False
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(line)
    r.font.name = 'Consolas'
    r.font.size = Pt(10)
    r.font.color.rgb = RGBColor(0,0,0)
    for attr in ('ascii','hAnsi','eastAsia','cs'):
        r._element.get_or_add_rPr().rFonts.set(qn('w:'+attr),'Consolas')
for element in (doc.element, doc.styles.element):
    for border in list(element.iter(qn('w:pBdr'))):
        border.getparent().remove(border)
doc.save(root / 'Сокращённый листинг MainForm.docx')
print('Source lines:', len(Path(r'C:\Users\apani\.codex\attachments\c8658cd8-b0eb-442b-9f95-4322a9da078a\Вставленный текст.txt').read_text(encoding='utf-8-sig').splitlines()))
print('Listing lines:',len(src.splitlines()))
print('Maximum line length:',max(map(len,src.splitlines())))
