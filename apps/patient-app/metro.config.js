const {getDefaultConfig} = require('@expo/metro-config');

const config = getDefaultConfig(__dirname);

// Handle SVG files
config.resolver.assetExts.push(
  // Images
  'png',
  'jpg',
  'jpeg',
  'gif',
  'webp',
  'svg',
  'ico',
  'ttf',
  'otf',
  'eot',
  'woff',
  'woff2',
);

// Transform SVG files with react-native-svg-transformer
config.transformer.babelTransformerPath =
  require.resolve('react-native-svg-transformer');
config.resolver.platforms = ['ios', 'android', 'native', 'web'];

module.exports = config;
