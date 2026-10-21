/* Editor interface language: plain Korean and plain English.
   The source code keeps its Korean strings as keys. On screen, every text node and
   tooltip of the editor (never of the edited site) is swapped for the chosen language,
   so the wording stays simple for people who have never built a web page.
   Elements marked translate="no" (names, paths, code, diffs) are left alone. */
(function () {
  "use strict";
  var KEY = "se-lang";
  var lang;
  try { lang = localStorage.getItem(KEY); } catch (e) {}
  if (lang !== "ko" && lang !== "en") lang = /^ko/i.test(navigator.language || "") ? "ko" : "en";

  // source text : [plain Korean (null = same), English]
  var D = {
    "사이트 편집기": [null, "Site Editor"],
    "홈 (프로젝트 목록)": ["처음 화면 (내 프로젝트)", "Home (my projects)"],
    "파일 ▾": ["메뉴 ▾", "Menu ▾"],
    "홈 · 다른 프로젝트 열기": ["처음 화면 · 다른 프로젝트", "Home · other projects"],
    "저장": [null, "Save"],
    "다른 이름으로 저장(복제)…": ["사본으로 저장…", "Save a copy…"],
    "이름 바꾸기…": [null, "Rename…"],
    "이름 바꾸기": [null, "Rename"],
    "버전 기록 · 되돌리기": ["이전 버전 보기 · 되돌리기", "Version history"],
    "내보내기 (zip 내려받기)": ["zip 파일로 내려받기", "Download as zip"],
    "탐색기에서 폴더 열기": ["폴더 열어 보기", "Show the folder"],
    "배포…": ["공개하기…", "Publish…"],
    "배포 대상(서버) 설정…": ["공개할 곳(서버) 설정…", "Where to publish…"],
    "자동 저장": [null, "Autosave"],
    "불러오는 중…": [null, "Loading…"],
    "실행 취소 (Ctrl+Z)": ["되돌리기 (Ctrl+Z)", "Undo (Ctrl+Z)"],
    "다시 실행 (Ctrl+Y)": ["다시 하기 (Ctrl+Y)", "Redo (Ctrl+Y)"],
    "코드 변경 보기": ["바뀐 내용 보기", "See changes"],
    "저장 전 변경 취소": ["저장 안 한 변경 버리기", "Discard unsaved changes"],
    "디자인": ["꾸미기", "Design"],
    "내용": [null, "Content"],
    "파일": ["코드", "Code"],
    "되돌리기 기록": ["이전 버전", "Versions"],
    "HTML 구조나 CSS를 직접 고칠 때 씁니다. 저장할 때마다 되돌리기 기록이 남습니다.":
      ["코드를 아는 분이 HTML·CSS 파일을 직접 고칠 때 씁니다. 저장할 때마다 이전 버전이 남습니다.",
       "For people who know code: edit the HTML/CSS files directly. Every save keeps the previous version."],
    "파일 저장": [null, "Save file"],
    "배포된 상태로 되돌리기": ["공개된 버전으로 되돌리기", "Back to the published version"],
    "저장하기 전 상태가 자동으로 남습니다. 복원해도 지금 상태가 먼저 기록되므로 다시 되돌릴 수 있습니다.":
      ["저장할 때마다 그 전 모습이 남습니다. 되돌려도 지금 모습이 먼저 남으니 언제든 다시 바꿀 수 있습니다.",
       "Every save keeps the version before it. Restoring keeps the current one too, so you can always go back."],
    "편집할 페이지": [null, "Page to edit"],
    "페이지에서 요소를 클릭하세요": ["페이지에서 바꿀 곳을 클릭하세요", "Click the part of the page you want to change"],
    "데스크톱": ["컴퓨터", "Computer"],
    "휴대폰": [null, "Phone"],
    "새로고침": [null, "Reload"],
    "사이트 편집 화면": [null, "Site being edited"],
    "닫기": [null, "Close"],
    "그대로": [null, "Keep as is"],
    "고정폭": ["고정폭 (코드 글꼴)", "Monospace"],
    "나눔고딕": [null, "Nanum Gothic"], "나눔명조": [null, "Nanum Myeongjo"], "고운돋움": [null, "Gowun Dodum"],
    "방금": [null, "just now"],
    "저장 중…": [null, "Saving…"],
    "변경 사항 저장 대기 중…": ["곧 저장됩니다…", "Saving in a moment…"],
    "저장하지 않은 변경 있음 (자동 저장 꺼짐)": ["저장 안 한 변경이 있어요 (자동 저장 꺼짐)", "Unsaved changes (autosave is off)"],
    "✓ 모든 변경 저장됨": ["✓ 저장됨", "✓ Saved"],
    " · 공개하려면 배포": [" · 아직 공개 전", " · not published yet"],
    "이 글자는 데이터 파일과 연결돼 있지 않습니다": ["이 글자는 여기서 바꿀 수 없습니다", "This text cannot be changed here"],
    "글자를 바꿨습니다 (저장 전)": ["글자를 바꿨습니다", "Text changed"],
    "순서를 바꿨습니다": [null, "Order changed"],
    "저장하기 전 상태로 되돌렸습니다": [null, "Back to how it was before saving"],
    "적용할 화면": ["어느 화면에 적용할까요", "Apply to"],
    "모든 화면": [null, "All screens"],
    "휴대폰에서만": [null, "Phones only"],
    "처음 쓰는 분을 위한 순서": ["처음이라면 이렇게 해 보세요", "New here? Try this"],
    "오른쪽 페이지에서 바꾸고 싶은 곳을 클릭하면 파란 테두리가 생깁니다.": [null, "Click the part of the page you want to change. A blue outline appears."],
    "테두리의 네모 손잡이를 끌면 크기가 바뀝니다. 절반·전체 같은 자리에 자석처럼 붙습니다 (Alt 를 누르면 안 붙음).":
      [null, "Drag the small squares on the outline to resize. It snaps to half, full and other handy sizes (hold Alt to stop snapping)."],
    "위에 뜬 막대의 ⠿ 이동을 끌거나 상자를 끌면 순서가 바뀝니다. 분홍 선이 들어갈 자리입니다.":
      [null, "Drag ⠿ Move on the small bar (or the box itself) to change the order. The pink line shows where it will go."],
    "글자를 두 번 클릭하면 바로 입력할 수 있고, 떠 있는 막대로 크기·글꼴·굵기·색·정렬을 바꿉니다. 일부 글자만 드래그해 고르면 그 글자만 바뀝니다.":
      [null, "Double-click text to type. Use the floating bar for size, font, bold, color and alignment. Select a few words to change only those."],
    "왼쪽 칸에서 간격·색·너비를 숫자로 정확히 맞출 수 있습니다.": [null, "Use the panel on the left to set spacing, colors and widths exactly."],
    "바뀐 내용은 저절로 저장됩니다. 다 됐으면 공개하기를 눌러 인터넷에 올립니다. 실수하면 ↶ (Ctrl+Z).":
      [null, "Changes save automatically. When you are done, click Publish to put the site online. Made a mistake? ↶ (Ctrl+Z)."],
    "바꿀 범위": ["어디까지 바꿀까요", "Change"],
    "이 요소만": ["이것만", "Just this one"],
    "(휴대폰에서만)": [null, "(phones only)"],
    "  (휴대폰에서만)": [null, "  (phones only)"],
    "이 글자는 사이트 스크립트가 언어에 맞춰 채웁니다. 글자 내용은 파일 탭에서 바꾸세요(디자인은 여기서 가능).":
      ["이 글자는 사이트가 언어에 맞춰 바꿔 넣습니다. 글자는 코드 탭에서 고치고, 모양은 여기서 바꿀 수 있습니다.",
       "The site fills in this text by language. Change the words in the Code tab; you can change how it looks here."],
    "✎ 글자 편집": ["✎ 글자 고치기", "✎ Edit text"],
    "이 범위 디자인 원래대로": ["꾸민 것 되돌리기", "Reset design"],
    "얇게 300": ["얇게", "Thin"], "보통 400": ["보통", "Normal"], "중간 500": ["조금 굵게", "Medium"],
    "약간 굵게 600": ["굵게", "Semi-bold"], "굵게 700": ["더 굵게", "Bold"], "아주 굵게 800": ["아주 굵게", "Extra bold"],
    "글자": [null, "Text"],
    "폰트": ["글꼴", "Font"],
    "크기 (rem · 1rem = 기본 글자 크기)": ["글자 크기 (보통 글자의 몇 배)", "Text size (× normal size)"],
    "굵기": [null, "Weight"],
    "색": ["글자 색", "Color"],
    "정렬": ["줄 맞춤", "Align"],
    "왼쪽": [null, "Left"], "가운데": [null, "Center"], "오른쪽": [null, "Right"], "위": [null, "Top"], "아래": [null, "Bottom"],
    "줄 간격 (배수)": ["줄 간격", "Line spacing"],
    "자간 (em)": ["글자 사이 간격", "Letter spacing"],
    "여백 · 위치": ["간격 · 위치", "Spacing · position"],
    "바깥 여백 (rem)": ["바깥 간격 (보통 글자의 몇 배)", "Space outside (× text size)"],
    "안쪽 여백 (rem)": ["안쪽 간격 (보통 글자의 몇 배)", "Space inside (× text size)"],
    "블록 가운데 놓기": ["가운데로 옮기기", "Center it"],
    "여백 원래대로": ["간격 되돌리기", "Reset spacing"],
    "자동": [null, "Auto"],
    "크기 · 모양": [null, "Size · shape"],
    "너비 (감싸는 칸 대비 %)": ["너비 (들어 있는 칸의 몇 %)", "Width (% of its container)"],
    "최대 너비 (rem)": ["최대 너비 (보통 글자의 몇 배)", "Max width (× text size)"],
    "최소 높이 (rem)": ["최소 높이 (보통 글자의 몇 배)", "Min height (× text size)"],
    "배경색": [null, "Background"],
    "모서리 둥글기 (rem)": ["모서리 둥글게", "Rounded corners"],
    "그림자": [null, "Shadow"], "없음": [null, "None"], "약하게": [null, "Soft"], "보통": [null, "Medium"],
    "원래대로": [null, "Reset"],
    "없음(투명)": ["없음 (투명)", "none (transparent)"],
    "반응형 주의": ["화면 크기 주의", "Screen-size warning"],
    "고르기": [null, "Select"],
    "이 규칙 지우기": ["이 꾸밈 지우기", "Remove this design change"],
    "디자인 규칙 (site-editor.css)": ["꾸민 내용 목록", "Design changes"],
    "아직 바꾼 디자인이 없습니다.": ["아직 꾸민 것이 없습니다.", "No design changes yet."],
    "원래 CSS 파일은 그대로 두고, 이 파일 하나에 규칙을 모읍니다. 파일과 <link> 한 줄을 지우면 모든 디자인 변경이 없어집니다.":
      ["원래 디자인 파일은 그대로 두고, 꾸민 내용만 site-editor.css 한 파일에 모읍니다.",
       "Your original design files stay untouched; changes are kept in one file, site-editor.css."],
    "프로필": [null, "Profile"], "이름": [null, "Name"], "프로필 사진": [null, "Profile photo"], "윗줄 (소속)": ["윗줄 (소속)", "Top line (affiliation)"],
    "한 줄 소개": [null, "One-line intro"], "소개 문단": [null, "Intro paragraph"], "GitHub 주소": [null, "GitHub link"], "이메일": [null, "Email"],
    "이력서 PDF 경로": ["이력서 PDF 위치", "Resume PDF"], "LinkedIn 주소": [null, "LinkedIn link"], "핵심 숫자": [null, "Key numbers"],
    "숫자": [null, "Number"], "설명": [null, "Description"], "소개 섹션": [null, "About"], "문단": [null, "Paragraphs"],
    "정보 줄": [null, "Info rows"], "항목": [null, "Item"], "값": [null, "Value"], "링크 주소": [null, "Link"],
    "프로젝트 카드": [null, "Project cards"], "대표 카드(가로 전체)": ["크게 보이는 카드", "Featured (full width)"], "분류": [null, "Category"],
    "기간": [null, "Period"], "제목": [null, "Title"], "요약": [null, "Summary"], "문제": [null, "Problem"], "내 역할": [null, "My role"],
    "성과 수치": [null, "Results"], "링크": [null, "Links"], "태그": [null, "Tags"], "카드 이미지": [null, "Card image"],
    "이미지": [null, "Image"], "대체 텍스트": ["그림 설명", "Image description"], "기술 스택": [null, "Skills"], "묶음 이름": [null, "Group name"],
    "이력": [null, "Experience"], "시기": [null, "When"], "한국어": [null, "Korean"],
    "이미지 없음": [null, "No image"], "3MB 이하 이미지만 올릴 수 있습니다": [null, "Images must be 3 MB or smaller"],
    "이미지를 넣었습니다": [null, "Image added"], "이미지 바꾸기": [null, "Change image"], "이미지 올리기": [null, "Add image"], "빼기": [null, "Remove"],
    "대체 텍스트 (화면 낭독기용)": ["그림 설명 (화면을 읽어 주는 프로그램용)", "Image description (for screen readers)"],
    "삭제": [null, "Delete"], "위로": [null, "Move up"], "아래로": [null, "Move down"], "복제": [null, "Duplicate"],
    "이 항목을 삭제할까요? (↶ 로 되돌릴 수 있습니다)": [null, "Delete this item? (↶ brings it back)"],
    "(비어 있음)": [null, "(empty)"],
    "이 페이지의 저장하지 않은 글자·순서 변경을 버리고 다른 페이지로 갈까요? (디자인·내용 변경은 유지)":
      [null, "Go to another page and drop the unsaved text/order changes on this one? (Design and content changes are kept.)"],
    "바뀐 파일이 없습니다": [null, "Nothing changed"],
    "저장하지 않은 변경을 모두 버릴까요?": ["저장 안 한 변경을 모두 버릴까요?", "Discard all unsaved changes?"],
    "새 이름": [null, "New name"],
    "이름을 바꿨습니다 (폴더와 배포 설정은 그대로)": ["이름을 바꿨습니다 (폴더와 공개 설정은 그대로)", "Renamed (folder and publish settings unchanged)"],
    "새 프로젝트 이름 (지금 내용을 복사해 새 프로젝트로 만듭니다)": [null, "Name for the copy (a new project with the current content)"],
    "(변경 없음)": [null, "(no changes)"],
    "저장하면 바뀌는 코드": ["저장하면 바뀌는 내용", "What saving will change"],
    "디자인·내용에 저장하지 않은 변경이 있습니다. 파일을 저장하면 화면이 새로 읽혀 그 변경은 사라집니다. 계속할까요?":
      ["꾸미기·내용에 저장 안 한 변경이 있습니다. 코드 파일을 저장하면 그 변경은 사라집니다. 계속할까요?",
       "You have unsaved design/content changes. Saving this code file will drop them. Continue?"],
    "파일을 저장했습니다": [null, "File saved"], "되돌렸습니다": [null, "Restored"], "아직 기록이 없습니다.": ["아직 이전 버전이 없습니다.", "No earlier versions yet."],
    "이 상태로 복원": ["이 버전으로 되돌리기", "Restore this version"], "복원했습니다": ["되돌렸습니다", "Restored"],
    "폴더 (로컬·네트워크 드라이브)": ["폴더 (내 PC·네트워크 드라이브)", "Folder (this PC or a network drive)"],
    "배포 대상 (서버) 설정": ["공개할 곳(서버) 설정", "Where to publish"],
    "접속 정보는 이 PC에만 저장됩니다. 비밀번호는 Windows 자격 증명 관리자(키체인)에 들어가고 이 화면에도 다시 보이지 않습니다. 사이트 저장소에는 아무것도 기록되지 않습니다.":
      ["접속 정보는 이 PC에만 저장됩니다. 비밀번호는 Windows 자격 증명 관리자에 안전하게 보관되고, 이 화면에도 다시 보이지 않습니다.",
       "Connection details stay on this PC. Passwords are kept in the Windows Credential Manager and are never shown again."],
    "비밀번호 저장됨": [null, "password saved"], "접속 시험": ["연결 확인", "Test connection"], "수정": [null, "Edit"],
    "+ 새 배포 대상": ["+ 공개할 곳 추가", "+ Add a place to publish"], "배포 대상 수정": ["공개할 곳 고치기", "Edit place to publish"],
    "새 배포 대상": ["공개할 곳 추가", "Add a place to publish"], "저장됨 (바꿀 때만 입력)": [null, "saved (type only to change it)"],
    "이름 (예: 학교 서버)": [null, "Name (e.g. school server)"],
    "공개 주소 (배포 후 확인용, 예: https://example.com/)": ["인터넷 주소 (올린 뒤 확인용, 예: https://example.com/)", "Web address (to check after publishing, e.g. https://example.com/)"],
    "서버 주소 (호스트)": [null, "Server address (host)"], "포트": [null, "Port"], "사용자 이름": [null, "User name"],
    "서버의 사이트 폴더 (예: /var/www/html)": [null, "Site folder on the server (e.g. /var/www/html)"],
    "키 파일 (권장)": [null, "Key file (recommended)"], "비밀번호": [null, "Password"], "로그인 방법": [null, "Sign-in method"],
    "개인 키 파일 경로 (예: C:/Users/나/.ssh/id_ed25519)": ["개인 키 파일 위치 (예: C:/Users/나/.ssh/id_ed25519)", "Private key file (e.g. C:/Users/me/.ssh/id_ed25519)"],
    "키 암호 (있을 때만)": [null, "Key passphrase (if any)"], "암호화(FTPS) 사용 — 권장": ["암호화해서 보내기 (FTPS) — 권장", "Encrypt (FTPS) — recommended"],
    "패시브 모드": ["패시브 모드 (잘 모르면 켜 두세요)", "Passive mode (leave on if unsure)"],
    "복사할 폴더 (예: Z:/www 또는 D:/backup/site)": [null, "Folder to copy to (e.g. Z:/www or D:/backup/site)"],
    "사이트 폴더가 git 저장소이면 자동으로 만들어집니다. 원격(origin)으로 push 합니다.":
      ["사이트 폴더가 GitHub 과 연결돼 있으면 자동으로 만들어집니다.", "Created automatically when the site folder is linked to GitHub."],
    "처음 접속할 때 서버 지문을 자동으로 기억합니다(accept-new). 이 PC의 OpenSSH(sftp)를 씁니다.":
      ["처음 접속한 서버를 기억해 두고 다음부터 같은 서버인지 확인합니다.", "The server is remembered on first connect and checked every time after."],
    "서버 종류": [null, "Server type"], "뒤로": [null, "Back"],
    "저장했습니다. '접속 시험'으로 확인해 보세요": ["저장했습니다. '연결 확인'을 눌러 보세요", "Saved. Try 'Test connection'."],
    "배포 — 공개 사이트에 올리기": ["공개하기 — 인터넷에 올리기", "Publish — put it online"],
    "아직 배포 대상이 없습니다. 서버를 먼저 등록하세요.": ["아직 공개할 곳이 없습니다. 서버를 먼저 추가하세요.", "No place to publish yet. Add a server first."],
    "배포 대상 추가": ["공개할 곳 추가", "Add a place to publish"], "올릴 곳": [null, "Publish to"], "배포 대상 관리": ["공개할 곳 관리", "Manage"],
    "저장하지 않은 변경이 있습니다. 저장한 것만 배포됩니다.": ["저장 안 한 변경이 있습니다. 저장한 것만 올라갑니다.", "There are unsaved changes. Only saved changes are published."],
    "직전 배포 되돌리기": ["지난번 공개 되돌리기", "Undo last publish"],
    "올릴 변경이 없습니다. 공개 사이트가 이미 최신입니다.": ["올릴 것이 없습니다. 인터넷의 사이트가 이미 최신입니다.", "Nothing to publish. The online site is up to date."],
    "이 서버에 처음 올립니다. 서버에 같은 이름의 파일이 있으면 먼저 내려받아 백업한 뒤 덮어씁니다.":
      [null, "First upload to this server. Files with the same name on the server are backed up first, then replaced."],
    "바뀐 내용 (초록 = 추가, 빨강 = 삭제)": ["바뀐 내용 (초록 = 더해짐, 빨강 = 빠짐)", "Changes (green = added, red = removed)"],
    "변경이 너무 커서 앞부분만 보여 줍니다.": [null, "Too many changes; showing the first part."],
    "무엇을 바꿨는지 한 줄 (예: 제목 글꼴·크기 변경)": ["무엇을 바꿨나요? (예: 제목 글꼴 바꿈)", "What did you change? (e.g. new title font)"],
    "변경 설명": ["메모", "Note"], "위 변경을 공개 사이트에 올리는 것을 확인했습니다": ["위 내용을 인터넷에 올려도 됩니다", "Yes, put these changes online"],
    "배포하기": ["공개하기", "Publish"], "취소": [null, "Cancel"],
    "마지막 커밋을 되돌리는 커밋을 만들어 push 합니다": ["지난번에 올린 것을 취소하는 변경을 올립니다", "Uploads a change that cancels the last publish"],
    "직전 배포 때 백업한 서버 파일을 다시 올리고, 그때 새로 올린 파일은 지웁니다":
      ["지난번에 백업해 둔 파일을 다시 올리고, 그때 새로 올린 파일은 지웁니다", "Puts back the files backed up last time and removes the ones added then"],
    "되돌리기": [null, "Undo"], "배포": ["공개", "Publish"], "진행 상황": [null, "Progress"], "사이트 열기 ↗": [null, "Open the site ↗"],
    "새 파일": [null, "new"], "새 사이트": [null, "New site"],
    // home
    "프로젝트 검색 (이름 · 폴더)": [null, "Search projects (name · folder)"], "설정": [null, "Settings"],
    "새로 시작하기": [null, "Start something"], "새로 만들기": [null, "New"], "빈 사이트에서 시작": [null, "Start from a blank site"],
    "링크로 가져오기": ["인터넷 주소로 가져오기", "Import from a link"], "사이트 주소를 넣으면 그대로 복사": [null, "Copy a site from its address"],
    "열기": [null, "Open"], "PC에 있는 사이트 폴더": [null, "A site folder on this PC"], "폴더 업로드": [null, "Upload folder"],
    "복사본을 보관함에 저장": [null, "Keeps a copy here"], "zip 업로드": [null, "Upload zip"], "압축 파일을 풀어 저장": [null, "Unpacks and keeps it"],
    "사이트 폴더나 zip 파일을 이 화면에 끌어다 놓아도 됩니다.": [null, "You can also drag a site folder or zip file onto this screen."],
    "최근 프로젝트": [null, "Recent projects"], "여기에 놓으면 업로드합니다": [null, "Drop here to upload"],
    "검색 결과가 없습니다.": [null, "No results."],
    "아직 프로젝트가 없습니다. 위에서 새로 만들거나, 사이트 폴더를 열거나 끌어다 놓으세요.":
      [null, "No projects yet. Create one above, open a site folder, or drag one here."],
    "미리보기 만드는 중…": [null, "Making preview…"], "HTML 페이지 없음": [null, "No HTML page"], "폴더를 찾을 수 없음": [null, "Folder not found"],
    "보관함": ["편집기 보관함", "Saved in editor"], "PC 폴더": ["내 PC 폴더", "Folder on this PC"], "더 보기": [null, "More"],
    "폴더를 찾을 수 없습니다. 목록에서 빼거나 다시 여세요": [null, "Folder not found. Remove it from the list or open it again."],
    "새 이름 (폴더와 배포 설정은 그대로)": ["새 이름 (폴더와 공개 설정은 그대로)", "New name (folder and publish settings unchanged)"],
    "사본 만들기": [null, "Make a copy"], "zip 으로 내보내기": ["zip 파일로 내려받기", "Download as zip"],
    "목록에서 빼기 (파일은 그대로)": [null, "Remove from list (files stay)"], "목록에서 뺐습니다": [null, "Removed from the list"],
    "삭제…": [null, "Delete…"], "프로젝트 삭제": [null, "Delete project"],
    "확인을 위해 프로젝트 이름을 입력하세요": [null, "Type the project name to confirm"], "휴지통으로 옮겼습니다": [null, "Moved to the trash"],
    "프로젝트 이름": [null, "Project name"], "만들기": [null, "Create"],
    "폴더 선택 창을 여는 중… (작업 표시줄에 숨어 있을 수 있습니다)": [null, "Opening the folder picker… (it may be behind this window)"],
    "폴더 열기": [null, "Open folder"],
    "사이트 폴더 경로 (index.html 이 있는 폴더)": ["사이트 폴더 위치 (index.html 이 들어 있는 폴더)", "Site folder (the one with index.html)"],
    "폴더는 옮기거나 복사하지 않고 그 자리에서 편집합니다.": [null, "The folder is edited where it is; nothing is moved or copied."],
    "비우면 사이트 주소로": ["비워 두면 사이트 주소로 정합니다", "Leave empty to use the site address"],
    "사이트 주소": [null, "Site address"],
    "최대 페이지 수 (같은 사이트 안의 링크를 따라가며 복사)": ["최대 페이지 수 (사이트 안의 링크를 따라가며 복사)", "Max pages (follows links inside the site)"],
    "스크립트로 그려지는 사이트 (화면 그대로 가져오기)": ["화면에 보이는 그대로 가져오기", "Copy exactly what the screen shows"],
    "React·Vue 처럼 자바스크립트가 내용을 그리는 사이트용. 화면 없는 Edge 로 열어 다 그려진 모습을 저장하고 스크립트는 뺍니다.":
      ["내용이 늦게 나타나는 사이트(React·Vue 등)용입니다. 다 보인 모습 그대로 저장합니다.", "For sites whose content appears after loading (React, Vue…). Saves the page as it finally looks."],
    "같은 사이트의 HTML · CSS · JS · 이미지 · 폰트를 복사하고 링크를 상대 경로로 바꿉니다. 다른 사이트(CDN 등) 링크는 그대로 둡니다. 내 사이트이거나 복사할 권리가 있는 사이트만 가져오세요.":
      ["그 사이트의 페이지·그림·글꼴을 복사해서 내 PC에서 바로 고칠 수 있게 만듭니다. 내 사이트이거나 복사할 권리가 있는 사이트만 가져오세요.",
       "Copies the site's pages, images and fonts so you can edit them on this PC. Only import sites you own or may copy."],
    "가져오기": [null, "Import"], "가져오는 중… 사이트 크기에 따라 몇십 초 걸릴 수 있습니다.": [null, "Importing… this can take a little while for big sites."],
    "준비 중…": [null, "Getting ready…"], "올릴 파일이 없습니다": [null, "No files to upload"],
    "200MB 보다 큰 폴더는 '열기'로 여세요": [null, "For folders over 200 MB, use 'Open' instead"],
    "업로드 중": [null, "Uploading"], "zip 푸는 중": [null, "Unpacking zip"], "업로드한 사이트": [null, "Uploaded site"],
    "켜 두면 바로가기를 누르자마자 창이 뜹니다. 창 없이 뒤에서 기다리기만 합니다.": [null, "The window opens instantly from the shortcut. It just waits in the background."],
    "Windows 를 켤 때 조용히 대기": ["Windows 를 켜면 미리 준비해 두기", "Get ready when Windows starts"],
    "보관함 위치 (새로 만들기 · 업로드 · 사본이 저장되는 곳)": ["보관함 위치 (새로 만든 · 올린 · 복사한 프로젝트가 저장되는 곳)", "Storage folder (for new, uploaded and copied projects)"],
    "이 사용자만 읽는 로컬 파일": [null, "a file only you can read"], "Windows 자격 증명 관리자": [null, "Windows Credential Manager"],
    "바탕화면 · 시작 메뉴 바로가기 만들기": [null, "Add desktop and Start menu shortcuts"], "바로가기를 만들었습니다": [null, "Shortcuts added"],
    "설정을 저장했습니다": [null, "Settings saved"], "언어": [null, "Language"],
    "폴더": [null, "Folder"],
    "{n}배": [null, "×{n}"],
    "선택:": ["고른 것:", "Selected:"], "선택: ": ["고른 것: ", "Selected: "], "휴대폰 화면에만 적용됩니다": [null, "Applies on phones only"],
    "제목": [null, "Title"], "소제목": [null, "Heading"], "글 문단": [null, "Paragraph"], "버튼": [null, "Button"], "구역": [null, "Section"],
    "상자": [null, "Box"], "목록 항목": [null, "List item"], "목록": [null, "List"], "메뉴": [null, "Menu"], "맨 위 부분": [null, "Top bar"],
    "맨 아래 부분": [null, "Footer"], "카드": [null, "Card"], "본문": [null, "Main area"], "굵은 글자": [null, "Bold text"],
    "기울인 글자": [null, "Italic text"], "그림 상자": [null, "Picture box"], "입력 양식": [null, "Form"], "입력 칸": [null, "Input"],
    "이름표": [null, "Label"], "표": [null, "Table"], "동영상": [null, "Video"], "옆 상자": [null, "Side box"], "작은 글자": [null, "Small text"],
    "요소": ["부분", "Part"], "그림": [null, "Picture"],
    "예시 사이트": [null, "Example site"], "예시 사이트로 시작하기": [null, "Start with the example site"],
    "예시 사이트 (카페)": [null, "Example site (café)"], "빈 사이트": [null, "Blank site"],
    "사진·메뉴 카드·소개가 들어 있는 완성된 한 쪽짜리 사이트. 바로 고쳐 보며 익히기 좋습니다.":
      [null, "A finished one-page site with photos, menu cards and an about section. Great for learning by changing things."],
    "제목과 글 두 칸만 있는 깨끗한 시작": [null, "A clean start with just a title and two text blocks"],
    "이 사이트에는 데이터 파일(content.js)이 없습니다. 디자인 탭에서 글자를 두 번 클릭해 바로 고치거나, 파일 탭을 쓰세요.":
      ["이 사이트에는 내용 칸이 없습니다. 꾸미기 탭에서 글자를 두 번 클릭해 바로 고치세요.",
       "This site has no content form. Double-click text in the Design tab to edit it directly."],
    "글자 편집을 먼저 끝내세요 (완료 또는 Ctrl+Enter)": ["글자 고치기를 먼저 끝내세요 (완료 또는 Ctrl+Enter)", "Finish editing the text first (Done or Ctrl+Enter)"],
    "예: C:\\Users\\나\\Documents\\my-site": [null, "e.g. C:\\Users\\me\\Documents\\my-site"],
    // floating toolbar (inside the page)
    "끌어서 순서 바꾸기": [null, "Drag to reorder"], "앞으로": [null, "Earlier"], "감싸는 요소 고르기": ["바깥 상자 고르기", "Select the outer box"],
    "글자 편집 (두 번 클릭)": ["글자 고치기 (두 번 클릭)", "Edit text (double-click)"], "작게": [null, "Smaller"], "크게": [null, "Bigger"],
    "굵게": [null, "Bold"], "기울임": [null, "Italic"], "글자 색": [null, "Text color"], "완료 (Ctrl+Enter)": [null, "Done (Ctrl+Enter)"],
    "취소 (Esc)": [null, "Cancel (Esc)"], "⠿ 이동": [null, "⠿ Move"], "⬑ 부모": ["⬑ 바깥", "⬑ Outer"], "✎ 글자": [null, "✎ Text"], "완료": [null, "Done"],
    "폰트 (그대로)": ["글꼴 (그대로)", "Font (keep)"], "옮길 수 있는 같은 줄의 블록이 없습니다": ["옆에 옮길 자리가 없습니다", "Nothing next to it to swap with"],
    "이미 맨 앞입니다": [null, "Already first"], "이미 맨 뒤입니다": [null, "Already last"],
    "이 글자는 언어 설정 스크립트가 채웁니다 (파일 탭에서 수정)": ["이 글자는 사이트가 언어에 맞춰 넣습니다 (코드 탭에서 고치세요)", "The site fills in this text by language (edit it in the Code tab)"],
    "이 요소는 바로 편집할 수 없습니다. 안쪽 글자를 두 번 클릭해 보세요": ["여기는 바로 고칠 수 없습니다. 안쪽 글자를 두 번 클릭해 보세요", "This can't be edited directly. Double-click the text inside it."],
    "선택한 글자에만 적용": [null, "Applied to the selected words"], "너비": [null, "Width"], "높이 자동": [null, "Height: auto"], "최소 높이": [null, "Min height"],
    "(Alt: 스냅 끄기)": ["(Alt: 자석 끄기)", "(Alt: no snapping)"],
    // messages from the server
    "nothing to deploy": ["올릴 것이 없습니다", "Nothing to publish"],
    "the files changed after you reviewed them; review again": ["확인한 뒤에 파일이 바뀌었습니다. 다시 확인해 주세요", "Files changed after you checked them; please check again"],
    "the files changed after you reviewed them; review the diff again": ["확인한 뒤에 파일이 바뀌었습니다. 다시 확인해 주세요", "Files changed after you checked them; please check again"],
    "deploy needs explicit confirmation": ["올려도 된다는 확인이 필요합니다", "Please confirm before publishing"],
    "no deploy to roll back": ["되돌릴 공개 기록이 없습니다", "Nothing to undo"]
  };
  // [pattern, Korean output, English output] — $1, $2 … are the captured parts; {t:$n} also translates that part
  var P = [
    [/^(\d+)초 전$/, "$1초 전", "$1 s ago"], [/^(\d+)분 전$/, "$1분 전", "$1 min ago"], [/^(\d+)시간 전$/, "$1시간 전", "$1 h ago"],
    [/^ · (.+) · 공개하려면 배포$/, " · {t:1} · 아직 공개 전", " · {t:1} · not published yet"],
    [/^선택: (.+)$/, "고른 것: $1", "Selected: $1"],
    [/^같은 종류 전부 \((\d+)개\)$/, "비슷한 것 모두 ($1개)", "All similar ($1)"],
    [/^CSS 규칙: (.+?)(  \(휴대폰에서만\))?$/, "바뀌는 곳: $1$2", "Applies to: $1{t:2}"],
    [/^(\d+)개$/, "$1개", "$1"], [/^(\d+)개 · 비어 있으면 숨김$/, "$1개 · 비어 있으면 숨김", "$1 · hidden when empty"],
    [/^\+ (.+) 추가$/, "+ {t:1} 추가", "+ Add {t:1}"],
    [/^(\d+)\. \(비어 있음\)$/, "$1. (비어 있음)", "$1. (empty)"],
    [/^저장했습니다: (.+) \(아직 공개 전\)$/, "저장했습니다: $1 (아직 공개 전)", "Saved: $1 (not published yet)"],
    [/^(저장|되돌리기|다시 실행|비교|불러오기) 실패: (.+)$/, "{t:1} 실패: {t:2}", "{t:1} failed: {t:2}"],
    [/^실패: (.+)$/, "실패: {t:1}", "Failed: {t:1}"], [/^시작하지 못했습니다: (.+)$/, "시작하지 못했습니다: {t:1}", "Could not start: {t:1}"],
    [/^바뀐 파일 (\d+)개$/, "바뀐 파일 $1개", "$1 changed file(s)"], [/^바뀌는 파일: $/, "바뀌는 파일: ", "Files that change: "],
    [/^(배포|되돌리기) 중…$/, "{t:1} 중…", "{t:1} in progress…"],
    [/^(배포|되돌리기) 완료 · 공개 사이트 파일이 올린 내용과 같은 것을 확인했습니다\. $/, "{t:1} 완료 · 인터넷의 사이트가 바뀐 것을 확인했습니다. ", "{t:1} done · the online site now matches. "],
    [/^(배포|되돌리기)은 끝났지만 공개 사이트가 아직 다릅니다\(캐시일 수 있음\)\. 잠시 뒤 다시 확인하세요\. $/, "{t:1}은 끝났지만 인터넷의 사이트가 아직 예전 모습입니다. 잠시 뒤 다시 확인하세요. ", "{t:1} finished, but the online site still shows the old version. Check again in a minute. "],
    [/^비밀값으로 보이는 내용이 있어 배포를 막았습니다: $/, "비밀번호·열쇠 같은 내용이 보여서 올리지 않았습니다: ", "Stopped: something that looks like a password or key was found: "],
    [/^아직 올라가지 않은 커밋도 함께 올라갑니다: $/, "지난번에 못 올린 변경도 함께 올라갑니다: ", "Earlier changes that were not published yet go too: "],
    [/^주소: $/, "주소: ", "Address: "], [/^   ·   위치: (.*)$/, "   ·   위치: $1", "   ·   Location: $1"],
    [/^수정 (.+) · (.+)$/, "고친 때: {t:1} · $2", "Edited {t:1} · $2"],
    [/^출처: (.+)$/, "가져온 곳: $1", "From: $1"], [/^배포: (.+)$/, "공개: $1", "Publishes to: $1"],
    [/^(\d+) \/ (\d+) 파일$/, "$1 / $2 파일", "$1 / $2 files"],
    [/^'(.+)' 를 만들었습니다$/, "'$1' 를 만들었습니다", "Created '$1'"],
    [/^보관함\((.+)\)에 빈 사이트를 만들고 바로 엽니다\.$/, "보관함($1)에 빈 사이트를 만들고 바로 엽니다.", "Creates a blank site in $1 and opens it."],
    [/^서버 비밀번호 보관: $/, "서버 비밀번호 보관: ", "Server passwords are kept in: "],
    [/^(.+): 너비 (.+) — 화면 밖으로 나갈 수 있습니다$/, "$1: 너비 $2 — 화면 밖으로 넘칠 수 있습니다", "$1: width $2 may overflow the screen"],
    [/^(.+): (.+) (.+) — 휴대폰보다 넓습니다\. % 를 쓰세요$/, "$1: $3 — 휴대폰보다 넓습니다. % 로 바꿔 보세요", "$1: $3 is wider than a phone; try a %"],
    [/^(.+): 고정 (.+) (.+) — 글자가 잘릴 수 있습니다$/, "$1: 높이 $3 고정 — 글자가 잘릴 수 있습니다", "$1: fixed height $3 can cut off text"],
    [/^지금 (.+)$/, "지금 $1", "now $1"],
    [/^너비 (.+)$/, "너비 $1", "Width $1"], [/^최소 높이 (.+)$/, "최소 높이 $1", "Min height $1"],
    [/^(.+) 을\(를\) 마지막 배포 상태로 되돌릴까요\? \(지금 상태는 기록에 남습니다\)$/, "$1 을(를) 공개된 버전으로 되돌릴까요? (지금 모습은 이전 버전에 남습니다)", "Put $1 back to the published version? (The current one is kept in Versions.)"],
    [/^(.+) 을\(를\) 이 시점으로 복원할까요\?$/, "$1 을(를) 이 버전으로 되돌릴까요?", "Restore $1 to this version?"],
    [/^(.+) 설정\(과 저장된 비밀번호\)을 지울까요\?$/, "$1 설정(과 저장된 비밀번호)을 지울까요?", "Delete $1 and its saved password?"],
    [/^'(.+)' 를 목록에서 뺄까요\?\n폴더와 파일은 지우지 않습니다\.$/, "'$1' 를 목록에서 뺄까요?\n폴더와 파일은 지우지 않습니다.", "Remove '$1' from the list?\nThe folder and files are not deleted."],
    [/^보관함에 있는 '(.+)' 폴더를 지웁니다\. (.+)$/, "보관함에 있는 '$1' 폴더를 지웁니다. 휴지통 폴더로 옮겨서 나중에 되살릴 수 있습니다.", "Deletes the '$1' folder from the editor's storage. It goes to a trash folder, so it can be recovered."],
    [/^(.+): 직전 배포를 되돌릴까요\?\n(.+)\.$/, "$1: 지난번 공개를 되돌릴까요?\n{t:2}.", "$1: undo the last publish?\n{t:2}."]
  ];

  function tr(s) {
    if (lang === "ko" && !D[s]) {  // Korean mode: only rewrite what has a plainer wording
      var hitK = pattern(s, 1);
      return hitK == null ? s : hitK;
    }
    var e = D[s];
    if (e) return lang === "en" ? e[1] : (e[0] == null ? s : e[0]);
    var hit = pattern(s, lang === "en" ? 2 : 1);
    return hit == null ? s : hit;
  }
  function pattern(s, col) {
    for (var i = 0; i < P.length; i++) {
      var m = P[i][0].exec(s);
      if (m) return P[i][col].replace(/\{t:(\d+)\}/g, function (_, n) { return m[+n] ? tr(m[+n]) : ""; })
        .replace(/\$(\d+)/g, function (_, n) { return m[+n] || ""; });
    }
    return null;
  }
  function T(s, vars) {
    var out = tr(s);
    if (vars) out = out.replace(/\{(\w+)\}/g, function (_, k) { return vars[k] != null ? vars[k] : ""; });
    return out;
  }
  function skip(node) {
    for (var n = node.nodeType === 1 ? node : node.parentNode; n && n.nodeType === 1; n = n.parentNode) {
      if (n.getAttribute("translate") === "no" || /^(SCRIPT|STYLE|TEXTAREA|PRE|CODE)$/.test(n.tagName)) return true;
    }
    return false;
  }
  var ATTRS = ["title", "placeholder", "aria-label"];
  function fixText(t) {
    var raw = t.nodeValue;
    if (t.__seDone === raw || !/[\uac00-\ud7a3]/.test(raw)) return;
    var out = tr(raw);                       // exact text first (some keys carry their own spaces)
    if (out === raw) {
      var core = raw.trim(), o2 = tr(core);  // then the text without surrounding spaces
      if (o2 !== core) out = raw.replace(core, o2);
    }
    t.__seDone = out;
    if (out !== raw) t.nodeValue = out;
  }
  function fixAttrs(el) {
    ATTRS.forEach(function (a) {
      var v = el.getAttribute(a);
      if (v && /[\uac00-\ud7a3]/.test(v) && el["__se_" + a] !== v) {
        var out = tr(v.trim());
        el["__se_" + a] = out;
        if (out !== v) el.setAttribute(a, out);
      }
    });
  }
  function walk(root) {
    if (root.nodeType === 3) { if (!skip(root)) fixText(root); return; }
    if (root.nodeType === 1 && skip(root)) return;
    if (root.nodeType === 1) fixAttrs(root);
    var w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, null);
    for (var n = w.nextNode(); n; n = w.nextNode()) {
      if (skip(n)) continue;
      if (n.nodeType === 3) fixText(n); else fixAttrs(n);
    }
  }
  function observe(root) {
    walk(root);
    new MutationObserver(function (list) {
      list.forEach(function (m) {
        if (m.type === "childList") m.addedNodes.forEach(walk);
        else if (m.type === "characterData") { if (!skip(m.target)) fixText(m.target); }
        else if (m.type === "attributes" && !skip(m.target)) fixAttrs(m.target);
      });
    }).observe(root, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }
  function setLang(l) { try { localStorage.setItem(KEY, l); } catch (e) {} location.reload(); }
  function langButton() {
    var b = document.createElement("button");
    b.type = "button"; b.className = "btn lang-btn";
    b.setAttribute("translate", "no");
    b.textContent = lang === "ko" ? "English" : "한국어";
    b.title = lang === "ko" ? "Switch to English" : "한국어로 보기";
    b.onclick = function () { setLang(lang === "ko" ? "en" : "ko"); };
    return b;
  }
  ["confirm", "prompt", "alert"].forEach(function (f) {
    var orig = window[f].bind(window);
    window[f] = function (msg, def) { return orig(tr(String(msg)), def); };
  });
  document.documentElement.lang = lang;
  window.SE_I18N = { lang: lang, T: T, tr: tr, observe: observe, walk: walk, setLang: setLang, langButton: langButton, dict: D, patterns: P };
  window.T = T;
  document.addEventListener("DOMContentLoaded", function () {
    observe(document.body);
    if (document.title) document.title = tr(document.title.split(" · ")[0]) + (document.title.indexOf(" · ") > 0 ? " · " + document.title.split(" · ").slice(1).join(" · ") : "");
    var slot = document.getElementById("langSlot");
    if (slot) slot.replaceWith(langButton());
  });
})();
