const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const webpack = require('webpack');

module.exports = {
  mode: 'development',
  entry: './src/index.js',
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: 'bundle.js',
    publicPath: '/'
  },
  module: {
    rules: [
      {
        test: /\.(js|jsx)$/,
        exclude: /node_modules/,
        use: {
          loader: 'babel-loader',
          options: {
            presets: ['@babel/preset-env', '@babel/preset-react'],
            plugins: ['@babel/plugin-transform-runtime']
          }
        }
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader']
      }
    ]
  },
  plugins: [
    new HtmlWebpackPlugin({
      template: './public/index.html'
    }),
    // Define environment variables that will be available in the browser
    new webpack.DefinePlugin({
      'process.env': {
        'REACT_APP_WS_URL': JSON.stringify(process.env.REACT_APP_WS_URL || 'ws://172.19.36.55:8000/ws')
      }
    }),
    new webpack.HotModuleReplacementPlugin()
  ],
  resolve: {
    extensions: ['.js', '.jsx'],
    modules: ['node_modules']
  },
  devServer: {
    host: '0.0.0.0',
    port: 3000,
    hot: true,
    historyApiFallback: true,
    open: false,
    client: {
      overlay: true,
      progress: true
    },
    static: {
      directory: path.join(__dirname, 'public')
    }
  },
  cache: {
    type: 'filesystem'
  },
  optimization: {
    removeAvailableModules: false,
    removeEmptyChunks: false,
    splitChunks: false,
  }
}; 