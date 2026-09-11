#!/usr/bin/python3

import re
import sys

F = sys.argv[1]

with open(F, 'rb') as f:
    content = f.read()

content = re.sub(br'L("([^"\\]|\\.)*")', br'U(\1)', content)
content = re.sub(br'\n(std::string StringFromWideString.*?\n\{[\s\S]+?\})', br'/*\1*/', content)
content = re.sub(br'\n(std::wstring WideStringFromString.*?\n\{[\s\S]+?\})', br'/*\1*/', content)
content = content.replace(b'std::wstring', b'std::string')
content = content.replace(b'std::string_convert', b'std::wstring_convert')

content = content.replace(b'boost/filesystem.hpp', b'filesystem')
content = content.replace(b'boost::filesystem', b'std::filesystem')

# ===== PATCH CHO AppleAPI.cpp =====
if F.endswith('AppleAPI.cpp'):

    # 1. Bỏ Windows includes
    content = content.replace(b'#include <WinSock2.h>\n', b'')
    content = content.replace(b'#include <windows.h>\n', b'')
    content = content.replace(b'#include <winhttp.h>\n', b'')
    content = content.replace(b'#include <WS2tcpip.h>\n', b'')
    content = content.replace(b'#pragma comment(lib, "winhttp.lib")\n', b'')
    content = content.replace(b'#pragma comment(lib, "winhttp.lib")', b'')

    # 2. Bỏ cpprestsdk compression extension
    content = content.replace(b'#include <cpprest/http_compression.h>\n', b'')
    content = content.replace(b'#include <cpprest/http_compression.h>', b'')

    # 3. Thay odslog: OutputDebugStringA -> fprintf
    content = content.replace(
        b'OutputDebugStringA(ss.str().c_str());',
        b'fprintf(stderr, "%s", ss.str().c_str());'
    )

    # 4. Đảm bảo có zlib + cstdio (thêm trước openssl/pem.h)
    if b'#include <zlib.h>' not in content:
        content = content.replace(
            b'#include <openssl/pem.h>',
            b'#include <zlib.h>\n#include <cstdio>\n#include <openssl/pem.h>'
        )

    # 5. Thay hàm decompress() dùng zlib thuần
    decompress_linux = br'''bool decompress(const uint8_t* input, size_t input_size, std::vector<uint8_t>& output)
{
    if (input == nullptr || input_size == 0) return false;

    z_stream strm = {};
    strm.next_in = const_cast<Bytef*>(input);
    strm.avail_in = (uInt)input_size;

    if (inflateInit2(&strm, 16 + MAX_WBITS) != Z_OK) return false;

    output.resize(input_size * 3);
    strm.next_out = output.data();
    strm.avail_out = (uInt)output.size();

    int ret;
    do {
        if (strm.avail_out == 0) {
            output.resize(output.size() * 2);
            strm.next_out = output.data() + strm.total_out;
            strm.avail_out = (uInt)(output.size() - strm.total_out);
        }
        ret = inflate(&strm, Z_NO_FLUSH);
    } while (ret == Z_OK);

    inflateEnd(&strm);
    if (ret != Z_STREAM_END) return false;

    output.resize(strm.total_out);
    return true;
}'''
    content = re.sub(
        br'bool decompress\(const uint8_t\* input[\s\S]+?return true;\n\}',
        decompress_linux,
        content
    )

    # 6. Thay gsaClient() - bỏ WinHttpSetOption, dùng set_keep_alive(false)
    gsa_linux = br'''web::http::client::http_client AppleAPI::gsaClient()
{
    http_client_config config;
    config.set_validate_certificates(false);
    // Fix 503: tat keep-alive de moi request dung connection moi
    config.set_keep_alive(false);
    return web::http::client::http_client(U("https://gsa.apple.com"), config);
}'''
    content = re.sub(
        br'web::http::client::http_client AppleAPI::gsaClient\(\)[\s\S]+?\n\}',
        gsa_linux,
        content
    )
# ===== HẾT PATCH AppleAPI.cpp =====


if F.endswith('AltServerApp.cpp'):

    # MessageBox
    # IDCANCEL
    # fs::path AltServerApp::appDataDirectoryPath
    content = content.replace(b'\r', b'')

    content = content.replace(b'#include <windows.h>\n', b'')
    content = content.replace(b'#include <windowsx.h>\n', b'')
    content = content.replace(b'#include <strsafe.h>\n', b'')
    content = content.replace(b'#include <ShlObj_core.h>\n', b'')
    content = content.replace(b'#include <winsparkle.h>\n', b'')
    content = content.replace(b'#pragma comment( lib, "gdiplus.lib" ) \n', b'')
    content = content.replace(b'#include <gdiplus.h> \n', b'')
    content = content.replace(b'#include "resource.h"\n', b'')

    def removePart(content, start, end):
        content = re.sub(br'\n' + start + br'[\S\s]+?(' + end + br')', br'\1', content)
        return content
    content = removePart(content, br'const char\* REGISTRY_ROOT_KEY', br'\nAltServerApp\* AltServerApp::_instance')
    content = removePart(content, br'static int CALLBACK BrowseFolderCallback', br'\npplx::task<std::shared_ptr<Application>> AltServerApp::InstallApplication')
    content = removePart(content, br'\n.*? AltServerApp::Authenticate', br'\npplx::task<std::shared_ptr<Team>> AltServerApp::FetchTeam')
    content = removePart(content, br'void AltServerApp::ShowNotification', br'\nvoid AltServerApp::ShowErrorAlert')
    content = removePart(content, br'bool AltServerApp::CheckDependencies', br'\nfs::path AltServerApp::certificatesDirectoryPath')

    def insertBefore(content, marker, newcontent):
        content = content.replace(marker, newcontent + b'\n' + marker)
        return content
    
    content = insertBefore(content, b'AltServerApp* AltServerApp::_instance = nullptr;', br'''
#define IDCANCEL 0
#define MessageBox(x, content, title, xx) (this->ShowAlert(title, content " (Ctrl-C to avoid)"), 1)

// Observes all exceptions that occurred in all tasks in the given range.
template<class T, class InIt>
void observe_all_exceptions(InIt first, InIt last)
{
	// TODO: FIX THIS
}
''')

    content = insertBefore(content, b'fs::path AltServerApp::certificatesDirectoryPath', br'''
HWND AltServerApp::windowHandle() const
{
	return _windowHandle;
}

HINSTANCE AltServerApp::instanceHandle() const
{
	return _instanceHandle;
}


bool AltServerApp::boolValueForRegistryKey(std::string key) const
{
	return false;
}

void AltServerApp::setBoolValueForRegistryKey(bool value, std::string key)
{
	return;
}

std::string AltServerApp::serverID() const
{
	//auto serverID = GetRegistryStringValue(SERVER_ID_KEY);
	//return serverID;
	return "1234567";
}

pplx::task<std::pair<std::shared_ptr<Account>, std::shared_ptr<AppleAPISession>>> AltServerApp::Authenticate(std::string appleID, std::string password, std::shared_ptr<AnisetteData> anisetteData)
{
	auto verificationHandler = [=](void)->pp;
lx::task<std::optional<std::string>> {
		return pplx::create_task([=]() -> std::optional<std::string> {
			std::cout << "Enter two factor code" << std::endl			std::string _verificationCode = "";
			std::cin >> _verificationCode;
			auto verificationCode = std::make_optional<std::string>(_verificationCode);
			_verificationCode = "";

			return verificationCode;
		});
	};

	return pplx::create_task([=]() {
		if (anisetteData == NULL)
		{
			throw ServerError(ServerErrorCode::InvalidAnisetteData);
		}

		return AppleAPI::getInstance()->Authenticate(appleID, password, anisetteData, verificationHandler);
	});
}

void AltServerApp::HandleAnisetteError(AnisetteError& error)
{
    this->ShowAlert("AnisetteData error: ", error.localizedDescription());
}

void AltServerApp::ShowNotification(std::string title, std::string message)
{
	std::cout << "Notify: " << title << std::endl << "    " << message << std::endl;
}


extern "C" int getchar();
void AltServerApp::ShowAlert(std::string title, std::string message)
{
	std::cout << "Alert: " << title << std::endl << "    " << message << std::endl;
	std::cout << "Press any key to continue..." << std::endl;
	//char a;
	//std::cin >> a;
	getchar();
}

fs::path AltServerApp::appDataDirectoryPath() const
{
	fs::path altserverDirectoryPath("./AltServerData");

	if (!fs::exists(altserverDirectoryPath))
	{
		fs::create_directory(altserverDirectoryPath);
	}

	return altserverDirectoryPath;
}

void AltServerApp::Start(HWND windowHandle, HINSTANCE instanceHandle)
{
	ConnectionManager::instance()->Start();

	// DeviceManager only needs 
	const char *isNoUSB = getenv("ALTSERVER_NO_SUBSCRIBE");
	if (!isNoUSB) {
		DeviceManager::instance()->Start();
	}
}

void AltServerApp::Stop()
{
}
''')

sys.stdout.buffer.write(content)
