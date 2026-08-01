import AppKit
import ApplicationServices
import Foundation

private let expectedProofKeys = [
    "window_visible",
    "new_task_navigation",
    "composer_editable",
    "task_files_navigation_available",
    "skills_navigation_available",
]

private func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

guard CommandLine.arguments.count == 2,
      let rawPID = Int32(CommandLine.arguments[1]),
      rawPID > 0 else {
    fail("usage: verify_macos_accessibility.swift PID")
}
guard AXIsProcessTrusted() else {
    fail("macOS Accessibility permission is required for installed task UI verification")
}

let application = AXUIElementCreateApplication(pid_t(rawPID))

private func attribute(_ element: AXUIElement, _ name: CFString) -> AnyObject? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name, &value) == .success else {
        return nil
    }
    return value
}

private func text(_ element: AXUIElement, _ name: CFString) -> String {
    attribute(element, name) as? String ?? ""
}

private func elementName(_ element: AXUIElement) -> String {
    for attributeName in [
        kAXTitleAttribute as CFString,
        kAXDescriptionAttribute as CFString,
        kAXValueAttribute as CFString,
    ] {
        let candidate = text(element, attributeName).trimmingCharacters(in: .whitespacesAndNewlines)
        if !candidate.isEmpty { return candidate }
    }
    return ""
}

private func children(_ element: AXUIElement) -> [AXUIElement] {
    attribute(element, kAXChildrenAttribute as CFString) as? [AXUIElement] ?? []
}

private func find(
    in root: AXUIElement,
    role expectedRole: String,
    names: Set<String>,
    maximumNodes: Int = 10_000
) -> AXUIElement? {
    var stack = [root]
    var visited = 0
    while let element = stack.popLast() {
        visited += 1
        if visited > maximumNodes { return nil }
        let role = text(element, kAXRoleAttribute as CFString)
        if role == expectedRole && names.contains(elementName(element)) {
            return element
        }
        stack.append(contentsOf: children(element).reversed())
    }
    return nil
}

private func waitFor(
    timeout: TimeInterval = 30,
    _ probe: () -> AXUIElement?
) -> AXUIElement? {
    let deadline = Date().addingTimeInterval(timeout)
    repeat {
        if let value = probe() { return value }
        Thread.sleep(forTimeInterval: 0.2)
    } while Date() < deadline
    return nil
}

guard let window = waitFor({
    let candidates = attribute(application, kAXWindowsAttribute as CFString) as? [AXUIElement]
    return candidates?.first(where: {
        text($0, kAXTitleAttribute as CFString) == "AI4HEOR"
    })
}) else {
    fail("installed AI4HEOR window was not exposed through Accessibility")
}
let minimized = attribute(window, kAXMinimizedAttribute as CFString) as? Bool ?? false
guard !minimized else { fail("installed AI4HEOR window is minimized") }

let newTaskNames: Set<String> = ["新建任务", "New task"]
guard let newTask = waitFor({
    find(in: window, role: kAXButtonRole as String, names: newTaskNames)
}) else {
    fail("installed AI4HEOR did not expose the New task action")
}
guard AXUIElementPerformAction(newTask, kAXPressAction as CFString) == .success else {
    fail("installed AI4HEOR New task action could not be pressed")
}

let composerNames: Set<String> = [
    "描述你要处理的研究问题或工作……",
    "描述研究问题或要处理的工作",
    "Describe the research question or work you want to address…",
]
guard let composer = waitFor({
    find(in: window, role: kAXTextAreaRole as String, names: composerNames)
}) else {
    fail("installed AI4HEOR did not expose the task composer")
}
let sentinel = "AI4HEOR installed task UI smoke"
guard AXUIElementSetAttributeValue(
    composer,
    kAXValueAttribute as CFString,
    sentinel as CFTypeRef
) == .success,
      text(composer, kAXValueAttribute as CFString) == sentinel else {
    fail("installed AI4HEOR task composer is not editable")
}
guard AXUIElementSetAttributeValue(
    composer,
    kAXValueAttribute as CFString,
    "" as CFTypeRef
) == .success else {
    fail("installed AI4HEOR task composer could not be cleared")
}

guard find(
    in: window,
    role: kAXButtonRole as String,
    names: ["任务文件", "Task files"]
) != nil else {
    fail("installed AI4HEOR did not expose Task files navigation")
}
guard find(
    in: window,
    role: kAXButtonRole as String,
    names: ["插件与技能", "Plugins & skills"]
) != nil else {
    fail("installed AI4HEOR did not expose Plugins and skills navigation")
}

let proof = Dictionary(uniqueKeysWithValues: expectedProofKeys.map { ($0, true) })
guard let encoded = try? JSONSerialization.data(withJSONObject: proof, options: [.sortedKeys]) else {
    fail("installed task UI proof could not be encoded")
}
FileHandle.standardOutput.write(encoded)
FileHandle.standardOutput.write(Data("\n".utf8))
