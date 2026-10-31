/* SILK Game Agent native Windows x64 GUI launcher — Win32 API only, no CRT.
   The linked executable embeds zipapp payload and extracts it to LOCALAPPDATA.
   Python 3.13+ must be installed; this dependency is reported in the GUI.
*/
#include <stddef.h>
#include <stdint.h>
#include "payload.inc"

typedef void *HANDLE;
typedef HANDLE HWND; typedef HANDLE HINSTANCE; typedef HANDLE HMENU;
typedef unsigned long DWORD; typedef unsigned short WORD;
typedef unsigned int UINT; typedef int BOOL; typedef long LONG;
typedef uintptr_t WPARAM; typedef intptr_t LPARAM, LRESULT;
typedef const wchar_t *LPCWSTR; typedef wchar_t *LPWSTR;
typedef LRESULT (__stdcall *WNDPROC)(HWND,UINT,WPARAM,LPARAM);
typedef struct {UINT style;WNDPROC lpfnWndProc;int cbClsExtra,cbWndExtra;HINSTANCE hInstance;HANDLE hIcon,hCursor,hbrBackground;LPCWSTR lpszMenuName,lpszClassName;} WNDCLASSW;
typedef struct {HWND hwnd;UINT message;WPARAM wParam;LPARAM lParam;DWORD time;LONG x,y;DWORD lPrivate;} MSG;
typedef struct {DWORD nLength;void *lpSecurityDescriptor;BOOL bInheritHandle;} SECURITY_ATTRIBUTES;
typedef struct {DWORD cb;LPWSTR lpReserved,lpDesktop,lpTitle;DWORD dwX,dwY,dwXSize,dwYSize,dwXCountChars,dwYCountChars,dwFillAttribute,dwFlags;WORD wShowWindow,cbReserved2;void *lpReserved2;HANDLE hStdInput,hStdOutput,hStdError;} STARTUPINFOW;
typedef struct {HANDLE hProcess,hThread;DWORD dwProcessId,dwThreadId;} PROCESS_INFORMATION;

__declspec(dllimport) HINSTANCE __stdcall GetModuleHandleW(LPCWSTR);
__declspec(dllimport) DWORD __stdcall GetModuleFileNameW(HINSTANCE,LPWSTR,DWORD);
__declspec(dllimport) BOOL __stdcall DestroyWindow(HWND);
__declspec(dllimport) DWORD __stdcall GetEnvironmentVariableW(LPCWSTR,LPWSTR,DWORD);
__declspec(dllimport) DWORD __stdcall SearchPathW(LPCWSTR,LPCWSTR,LPCWSTR,DWORD,LPWSTR,LPWSTR*);
__declspec(dllimport) BOOL __stdcall CreateDirectoryW(LPCWSTR,void *);
__declspec(dllimport) DWORD __stdcall GetFileAttributesW(LPCWSTR);
__declspec(dllimport) HANDLE __stdcall CreateFileW(LPCWSTR,DWORD,DWORD,SECURITY_ATTRIBUTES*,DWORD,DWORD,HANDLE);
__declspec(dllimport) BOOL __stdcall WriteFile(HANDLE,const void*,DWORD,DWORD*,void*);
__declspec(dllimport) BOOL __stdcall ReadFile(HANDLE,void*,DWORD,DWORD*,void*);
__declspec(dllimport) BOOL __stdcall CloseHandle(HANDLE);
__declspec(dllimport) HANDLE __stdcall CreateThread(void*,size_t,DWORD (__stdcall*)(void*),void*,DWORD,DWORD*);
__declspec(dllimport) DWORD __stdcall WaitForSingleObject(HANDLE,DWORD);
__declspec(dllimport) BOOL __stdcall GetExitCodeProcess(HANDLE,DWORD*);
__declspec(dllimport) BOOL __stdcall CreateProcessW(LPCWSTR,LPWSTR,void*,void*,BOOL,DWORD,void*,LPCWSTR,STARTUPINFOW*,PROCESS_INFORMATION*);
__declspec(dllimport) DWORD __stdcall GetLastError(void);
__declspec(dllimport) int __stdcall MultiByteToWideChar(UINT,DWORD,const char*,int,LPWSTR,int);
__declspec(dllimport) int __stdcall WideCharToMultiByte(UINT,DWORD,LPCWSTR,int,char*,int,const char*,BOOL*);
__declspec(dllimport) void __stdcall ExitProcess(UINT);
__declspec(dllimport) HINSTANCE __stdcall ShellExecuteW(HWND,LPCWSTR,LPCWSTR,LPCWSTR,LPCWSTR,int);
__declspec(dllimport) int __stdcall MessageBoxW(HWND,LPCWSTR,LPCWSTR,UINT);
__declspec(dllimport) WORD __stdcall RegisterClassW(const WNDCLASSW*);
__declspec(dllimport) HWND __stdcall CreateWindowExW(DWORD,LPCWSTR,LPCWSTR,DWORD,int,int,int,int,HWND,HMENU,HINSTANCE,void*);
__declspec(dllimport) LRESULT __stdcall DefWindowProcW(HWND,UINT,WPARAM,LPARAM);
__declspec(dllimport) BOOL __stdcall ShowWindow(HWND,int);
__declspec(dllimport) BOOL __stdcall UpdateWindow(HWND);
__declspec(dllimport) int __stdcall GetMessageW(MSG*,HWND,UINT,UINT);
__declspec(dllimport) BOOL __stdcall TranslateMessage(const MSG*);
__declspec(dllimport) LRESULT __stdcall DispatchMessageW(const MSG*);
__declspec(dllimport) void __stdcall PostQuitMessage(int);
__declspec(dllimport) BOOL __stdcall PostMessageW(HWND,UINT,WPARAM,LPARAM);
__declspec(dllimport) uintptr_t __stdcall SetTimer(HWND,uintptr_t,UINT,void*);
__declspec(dllimport) BOOL __stdcall KillTimer(HWND,uintptr_t);
__declspec(dllimport) BOOL __stdcall SetWindowTextW(HWND,LPCWSTR);
__declspec(dllimport) int __stdcall GetWindowTextW(HWND,LPWSTR,int);
__declspec(dllimport) LRESULT __stdcall SendMessageW(HWND,UINT,WPARAM,LPARAM);
__declspec(dllimport) HANDLE __stdcall GetStockObject(int);

#define WS_CHILD 0x40000000UL
#define WS_VISIBLE 0x10000000UL
#define WS_BORDER 0x00800000UL
#define WS_TABSTOP 0x00010000UL
#define WS_VSCROLL 0x00200000UL
#define WS_OVERLAPPEDWINDOW 0x00CF0000UL
#define WS_CLIPCHILDREN 0x02000000UL
#define ES_MULTILINE 0x0004UL
#define ES_AUTOVSCROLL 0x0040UL
#define ES_READONLY 0x0800UL
#define ES_AUTOHSCROLL 0x0080UL
#define WM_CREATE 0x0001
#define WM_DESTROY 0x0002
#define WM_COMMAND 0x0111
#define WM_TIMER 0x0113
#define FILE_SHARE_WRITE 0x00000002UL
#define FILE_SHARE_DELETE 0x00000004UL
#define WM_SETFONT 0x0030
#define WM_APP 0x8000
#define GENERIC_READ 0x80000000UL
#define GENERIC_WRITE 0x40000000UL
#define FILE_SHARE_READ 1UL
#define CREATE_ALWAYS 2UL
#define OPEN_EXISTING 3UL
#define FILE_ATTRIBUTE_NORMAL 0x80UL
#define INVALID_FILE_ATTRIBUTES 0xffffffffUL
#define CREATE_NO_WINDOW 0x08000000UL
#define CREATE_NEW_CONSOLE 0x00000010UL
#define STARTF_USESTDHANDLES 0x00000100UL
#define INFINITE 0xffffffffUL
#define CP_UTF8 65001
#define SW_SHOW 5

static HWND g_hwnd,g_input,g_output,g_session_label,g_buttons[15];
static wchar_t g_root[768],g_bundle[896],g_py[768],g_queryfile[896],g_logfile[896],g_exepath[896],g_sessionfile[896];
static wchar_t g_result[24000];
static wchar_t g_action[30];
static int g_busy=0,g_using_launcher=0;
static const wchar_t *g_actions[15]={L"status",L"update",L"search",L"ask",L"replay",L"observer",L"rollback",L"step",L"session",L"nav",L"nav2",L"probe-install",L"environment",L"object-preview",L"object-nav"};
static const wchar_t *g_labels[15]={L"Состояние",L"Обновить",L"Поиск Wiki",L"Спросить Gemma",L"Отчёт из лога",L"Наблюдать OpenMW",L"Откат",L"Тест шага W (4с)",L"Запустить игровую сессию",L"Микромаршрут X/Y (до 6 шагов)",L"Навигация 2.0 · маршрут из 1–3 точек",L"Установить зонд (опц.)",L"Осмотреть местность",L"ЭКСП: осмотреть ближайшую дверь",L"ЭКСП: подойти к двери"};

static int slen(const wchar_t *x){int n=0;while(x[n])n++;return n;}
static int append(wchar_t*buf,int max,const wchar_t*src){int n=slen(buf),i=0;while(src[i]&&n+i+1<max){buf[n+i]=src[i];i++;}buf[n+i]=0;return src[i]==0;}
static void copyw(wchar_t*dst,int max,const wchar_t*src){dst[0]=0;append(dst,max,src);}
static void clearbuf(void*ptr,size_t n){unsigned char *p=(unsigned char*)ptr;while(n--)*p++=0;}
static void setresult(const wchar_t*msg){copyw(g_result,24000,msg);PostMessageW(g_hwnd,WM_APP+1,0,0);}
static int init_files(){
 DWORD n=GetEnvironmentVariableW(L"LOCALAPPDATA",g_root,650);
 if(n==0||n>=650)return 0;
 if(!append(g_root,768,L"\\SILK Game Agent"))return 0;
 CreateDirectoryW(g_root,0);
 copyw(g_bundle,896,g_root);append(g_bundle,896,L"\\app-bundle-BUNDLE_CACHE_TOKEN.zip");
 copyw(g_queryfile,896,g_root);append(g_queryfile,896,L"\\question.txt");
 copyw(g_logfile,896,g_root);append(g_logfile,896,L"\\last-command.log");
 copyw(g_sessionfile,896,g_root);append(g_sessionfile,896,L"\\_system\\session\\session_state.txt");
 if(GetFileAttributesW(g_bundle)==INVALID_FILE_ATTRIBUTES){
   HANDLE h=CreateFileW(g_bundle,GENERIC_WRITE,0,0,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,0);
   if(h==(HANDLE)(intptr_t)-1)return 0;
   DWORD done=0;
   BOOL ok=WriteFile(h,payload_bytes,(DWORD)sizeof(payload_bytes),&done,0);
   CloseHandle(h);
   if(!ok||done!=(DWORD)sizeof(payload_bytes))return 0;
 }
 if(GetModuleFileNameW(0,g_exepath,896)==0)return 0;
 if(SearchPathW(0,L"py.exe",0,768,g_py,0))g_using_launcher=1;
 else if(SearchPathW(0,L"python.exe",0,768,g_py,0))g_using_launcher=0;
 else return 2;
 return 1;
}
static int write_question(void){
 static wchar_t query[8000]; static char utf8[32000];DWORD written=0;
 int len=GetWindowTextW(g_input,query,8000);
 if(!len)return 0;
 int size=WideCharToMultiByte(CP_UTF8,0,query,len,utf8,32000,0,0);
 if(size<=0)return 0;
 HANDLE h=CreateFileW(g_queryfile,GENERIC_WRITE,0,0,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,0);
 if(h==(HANDLE)(intptr_t)-1)return 0;
 BOOL ok=WriteFile(h,utf8,(DWORD)size,&written,0);CloseHandle(h);
 return ok&&written==(DWORD)size;
}
static int command_line(wchar_t *cmd,int max){
 cmd[0]=0;
 append(cmd,max,L"\"");append(cmd,max,g_py);append(cmd,max,L"\" ");
 if(g_using_launcher)append(cmd,max,L"-3 ");
 append(cmd,max,L"\"");append(cmd,max,g_bundle);append(cmd,max,L"\" ");
 append(cmd,max,g_action);
 if(g_action[0]==L'o' && g_action[6]==L'-' && g_action[7]==L'n')append(cmd,max,L" --experimental-consent");
 if(g_action[0]==L's'&&g_action[1]==L'e'&&g_action[2]==L'a' || g_action[0]==L'a'&&g_action[1]==L's'&&g_action[2]==L'k' || g_action[0]==L'n'&&g_action[1]==L'a'&&g_action[2]==L'v' || g_action[0]==L'o'&&g_action[1]==L'b'&&g_action[2]==L'j'){
   append(cmd,max,L" --query-file \"");append(cmd,max,g_queryfile);append(cmd,max,L"\"");
 }
 if((g_action[0]==L'u'&&g_action[1]==L'p') || (g_action[0]==L'r'&&g_action[1]==L'o')){
   append(cmd,max,L" --host-exe \"");append(cmd,max,g_exepath);append(cmd,max,L"\"");
 }
 return 1;
}
static DWORD __stdcall worker(void*unused){
 (void)unused;
 static wchar_t command[4000]; command_line(command,4000);
 SECURITY_ATTRIBUTES sec;clearbuf(&sec,sizeof(sec));sec.nLength=sizeof(sec);sec.bInheritHandle=1;
 HANDLE out=CreateFileW(g_logfile,GENERIC_WRITE,FILE_SHARE_READ,&sec,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,0);
 HANDLE nul=CreateFileW(L"NUL",GENERIC_READ,FILE_SHARE_READ,&sec,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,0);
 if(out==(HANDLE)(intptr_t)-1||nul==(HANDLE)(intptr_t)-1){setresult(L"Не получилось открыть служебный журнал.");return 1;}
 STARTUPINFOW si;PROCESS_INFORMATION pi;clearbuf(&si,sizeof(si));clearbuf(&pi,sizeof(pi));
 si.cb=sizeof(si);si.dwFlags=STARTF_USESTDHANDLES;si.hStdInput=nul;si.hStdOutput=out;si.hStdError=out;
 BOOL ok=CreateProcessW(0,command,0,0,1,CREATE_NO_WINDOW,0,g_root,&si,&pi);
 CloseHandle(nul);CloseHandle(out);
 if(!ok){setresult(L"Не удалось запустить Python. Убедись, что команда py -3 работает в PowerShell.");return 1;}
 WaitForSingleObject(pi.hProcess,INFINITE);
 DWORD exitcode=0;GetExitCodeProcess(pi.hProcess,&exitcode);
 CloseHandle(pi.hProcess);CloseHandle(pi.hThread);
 HANDLE log=CreateFileW(g_logfile,GENERIC_READ,FILE_SHARE_READ,0,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,0);
 if(log==(HANDLE)(intptr_t)-1){setresult(L"Процесс завершён, но журнал недоступен.");return 1;}
 static char bytes[64000];DWORD got=0;
 ReadFile(log,bytes,63990,&got,0);CloseHandle(log);
 int w=MultiByteToWideChar(CP_UTF8,0,bytes,(int)got,g_result,23800);
 if(!w){copyw(g_result,24000,L"Ошибка чтения отчёта UTF-8");} else {g_result[w]=0;}
 if(exitcode==42){
   append(g_result,24000,L"\r\nСейчас будет выполнена замена оболочки EXE и перезапуск.");
 } else if(exitcode){append(g_result,24000,L"\r\n\r\nОперация завершена с ошибкой. Предыдущая рабочая версия не удалена.");}
 PostMessageW(g_hwnd,WM_APP+1,0,0);
 if(exitcode==42)PostMessageW(g_hwnd,WM_APP+3,0,0);
 return 0;
}
static void refresh_session_status(void){
 if(!g_session_label||g_busy)return;
 HANDLE h=CreateFileW(g_sessionfile,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,0,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,0);
 if(h==(HANDLE)(intptr_t)-1)return;
 char bytes[1400];DWORD count=0;
 BOOL ok=ReadFile(h,bytes,1390,&count,0);CloseHandle(h);
 if(!ok||count==0)return;
 wchar_t wide[1400];int len=MultiByteToWideChar(CP_UTF8,0,bytes,(int)count,wide,1399);
 if(len<=0)return;wide[len]=0;
 SetWindowTextW(g_session_label,wide);
}
static void start_action(int id){
 if(id<0||id>14||g_busy)return;
 if(id==7 && MessageBoxW(g_hwnd,L"SILK отправит один короткий шаг W (0,2 секунды) ТОЛЬКО в активное окно OpenMW.\n\nПосле нажатия Да переключись в OpenMW за 4 секунды (Alt+Tab).\nESC отменяет действие. Запусти игру в безопасном месте.\n\nПродолжить?",L"Подтверждение первого шага",0x34)!=6)return;
 if(id==9 && MessageBoxW(g_hwnd,L"Экспериментальный маршрут: SILK сначала калибрует W/D и затем выполнит максимум 6 коротких WASD-команд, сравнивая координаты после каждого действия.\n\nУкажи в верхнем поле относительное смещение X,Y, например 35,15 (15–90 игровых единиц).\n\nИспользуй только ровное пустое место БЕЗ NPC, обрывов и опасностей. Переключись в OpenMW за 4 секунды; не нажимай кнопки движения. ESC — стоп.\n\nПродолжить?",L"Согласие на микронавигацию",0x34)!=6)return;
 if(id==10 && MessageBoxW(g_hwnd,L"Navigation 2.0: до трёх относительных маршрутных точек X,Y через точку с запятой, например 35,15; 65,15; 65,-20.\n\nДве калибровки W/D, до 12 коротких WASD-команд ВКЛЮЧАЯ калибровку. Проверка координат после каждого движения. Преграды, смена направления, потеря фокуса или ESC останавливают маршрут.\n\nТолько ровная безопасная площадка. Переключись в OpenMW за 4 секунды, не нажимай WASD.\n\nНачать?",L"Согласие на Navigation 2.0",0x34)!=6)return;
 if(id==11 && MessageBoxW(g_hwnd,L"Установить НЕОБЯЗАТЕЛЬНЫЙ read-only Lua-зонд для наблюдения направления взгляда, ближайших дверей и существ?\n\nНужно сначала ЗАКРЫТЬ OpenMW. SILK создаст резервную копию openmw.cfg и добавит отдельный мод только наблюдения. Никакого управления, изменения сохранений и отключения прежнего зонда.\n\nПродолжить?",L"Дополнительная телеметрия OpenMW 0.51",0x34)!=6)return;
 if(id==14 && MessageBoxW(g_hwnd,L"ЭКСПЕРИМЕНТ: SILK попытается приблизиться к двери только по прямым координатам. Обход стен, скал, обрывов и переход через дверь НЕ поддерживаются.\n\nРазрешено только на безопасной открытой площадке с видимой дверью. Максимум 12 команд, ESC и потеря фокуса останавливают управление.\n\nСначала проверь кнопку предпросмотра и укажи индекс двери (0,1...). Переключись в OpenMW в течение 4 секунд.\n\nЯвно разрешить управление?",L"Эксперимент: навигация к двери",0x34)!=6)return;
 if(id==6 && MessageBoxW(g_hwnd,L"Вернуть предыдущую установленную версию агента?\nБаза и установленные файлы сохранятся.",L"Подтверждение отката",0x34)!=6)return;
 if(id==2||id==3||id==9||id==10||id==13||id==14){if(!write_question()){SetWindowTextW(g_output,L"Напиши запрос в поле над кнопками.");return;}}
 copyw(g_action,30,g_actions[id]);
 if(id==5){
   static wchar_t command[4000];command_line(command,4000);
   STARTUPINFOW si;PROCESS_INFORMATION pi;clearbuf(&si,sizeof(si));clearbuf(&pi,sizeof(pi));si.cb=sizeof(si);
   if(CreateProcessW(0,command,0,0,0,CREATE_NEW_CONSOLE,0,g_root,&si,&pi)){
     CloseHandle(pi.hProcess);CloseHandle(pi.hThread);
     SetWindowTextW(g_output,L"Наблюдатель OpenMW открыт в отдельной консоли. Для остановки нажми Ctrl+C в её окне.\r\nАвтономное управление игрой пока не реализовано.");
   }else SetWindowTextW(g_output,L"Не удалось открыть наблюдатель.");
   return;
 }
 if(id==10) SetWindowTextW(g_output,L"Navigation 2.0: переходи в игру за 4 секунды. ESC — стоп. До 12 движений по максимум трём точкам.");
 else if(id==9) SetWindowTextW(g_output,L"Микромаршрут: переключись в OpenMW за 4 секунды. НЕ трогай WASD, ESC — остановка. Будет не более 8 коротких команд (две калибровки и до шести шагов).");
 else if(id==7) SetWindowTextW(g_output,L"Один шаг W: переключись в окно OpenMW (Alt+Tab) в течение 4 секунд. ESC — отмена. Жду результатов телеметрии...");
 else SetWindowTextW(g_output,L"Выполняю команду... Для вопроса к Gemma потребуется запущенная Ollama.");
 g_busy=1;
 HANDLE thread=CreateThread(0,0,worker,0,0,0);
 if(thread)CloseHandle(thread);else{g_busy=0;SetWindowTextW(g_output,L"Не удалось создать рабочий поток.");}
}
static HWND child(LPCWSTR cls,LPCWSTR caption,DWORD style,int x,int y,int w,int h,int id){
 HWND c=CreateWindowExW(0,cls,caption,WS_CHILD|WS_VISIBLE|style,x,y,w,h,g_hwnd,(HMENU)(intptr_t)id,GetModuleHandleW(0),0);
 SendMessageW(c,WM_SETFONT,(WPARAM)GetStockObject(17),1);
 return c;
}
static LRESULT __stdcall window_proc(HWND hwnd,UINT message,WPARAM wp,LPARAM lp){
 (void)lp;
 if(message==WM_CREATE){
   g_hwnd=hwnd;
   child(L"STATIC",L"SILK GAME AGENT     •     Единое приложение  •  Энциклопедия / Gemma / OpenMW / обновления",0,18,14,825,25,99);
   child(L"STATIC",L"Вопрос для Wiki/Gemma или смещение X,Y для маршрута:",0,18,50,600,22,98);
   g_input=child(L"EDIT",L"Where is the Mages Guild in Balmora?",WS_BORDER|ES_AUTOHSCROLL|WS_TABSTOP,18,77,827,28,80);
   for(int i=0;i<9;i++)g_buttons[i]=child(L"BUTTON",g_labels[i],WS_TABSTOP,18+(i%3)*279,120+(i/3)*42,269,32,100+i);
   g_buttons[9]=child(L"BUTTON",g_labels[9],WS_TABSTOP,18,246,827,32,109);
   g_buttons[10]=child(L"BUTTON",g_labels[10],WS_TABSTOP,18,284,827,32,110);
   g_buttons[11]=child(L"BUTTON",g_labels[11],WS_TABSTOP,18,322,409,32,111);
   g_buttons[12]=child(L"BUTTON",g_labels[12],WS_TABSTOP,436,322,409,32,112);
   g_buttons[13]=child(L"BUTTON",g_labels[13],WS_TABSTOP,18,362,409,32,113);
   g_buttons[14]=child(L"BUTTON",g_labels[14],WS_TABSTOP,436,362,409,32,114);
   g_session_label=child(L"STATIC",L"Игровая сессия: не запущена · управление выключено",0,18,402,830,25,97);
   child(L"STATIC",L"Результат / состояние:",0,18,432,600,23,96);
   g_output=child(L"EDIT",L"Первый запуск автоматически перенесёт базу и проверит агент.\r\nПожалуйста, не перемещай старую энциклопедию, пока проверка не завершена.",WS_BORDER|ES_MULTILINE|ES_AUTOVSCROLL|WS_VSCROLL|ES_READONLY,18,459,827,265,95);
   SetTimer(hwnd,1,2000,0);
   PostMessageW(hwnd,WM_APP+2,0,0);
   return 0;
 }
 if(message==WM_COMMAND){int id=(int)(wp&0xffff);if(id>=100&&id<=114)start_action(id-100);return 0;}
 if(message==WM_TIMER){if(wp==1)refresh_session_status();return 0;}
 if(message==WM_APP+2){int r=init_files();if(r==0)SetWindowTextW(g_output,L"Не удалось подготовить служебную папку в LOCALAPPDATA.");else if(r==2)SetWindowTextW(g_output,L"Не найден Python! Для этой сборки нужен установленный Python 3.13+ и команда py -3. Никакие файлы игры не изменены.");else start_action(0);return 0;}
 if(message==WM_APP+1){SetWindowTextW(g_output,g_result);g_busy=0;return 0;}
 if(message==WM_APP+3){DestroyWindow(hwnd);return 0;}
 if(message==WM_DESTROY){KillTimer(hwnd,1);PostQuitMessage(0);return 0;}
 return DefWindowProcW(hwnd,message,wp,lp);
}
void start(void){
 HINSTANCE instance=GetModuleHandleW(0); WNDCLASSW wc; clearbuf(&wc,sizeof(wc));
 wc.lpfnWndProc=window_proc;wc.hInstance=instance;wc.hbrBackground=(HANDLE)(intptr_t)6;wc.lpszClassName=L"SILK_Game_Agent_Main";
 if(!RegisterClassW(&wc))ExitProcess(1);
 HWND hwnd=CreateWindowExW(0,wc.lpszClassName,L"SILK Game Agent — Stable + Experimental Navigation Candidate",WS_OVERLAPPEDWINDOW|WS_CLIPCHILDREN,170,100,881,811,0,0,instance,0);
 if(!hwnd)ExitProcess(1);
 ShowWindow(hwnd,SW_SHOW);UpdateWindow(hwnd);
 MSG msg;while(GetMessageW(&msg,0,0,0)>0){TranslateMessage(&msg);DispatchMessageW(&msg);}
 ExitProcess(0);
}
