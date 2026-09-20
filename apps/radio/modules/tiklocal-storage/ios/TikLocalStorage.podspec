Pod::Spec.new do |s|
  s.name           = 'TikLocalStorage'
  s.version        = '1.0.0'
  s.summary        = 'TikLocal app storage policy bridge'
  s.description    = 'Marks imported offline media as excluded from iCloud device backup.'
  s.author         = 'TikLocal'
  s.homepage       = 'https://docs.expo.dev/modules/'
  s.platforms      = {
    :ios => '16.4',
    :tvos => '16.4'
  }
  s.source         = { git: '' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'

  # Swift/Objective-C compatibility
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
  }

  s.source_files = "**/*.{h,m,mm,swift,hpp,cpp}"
end
