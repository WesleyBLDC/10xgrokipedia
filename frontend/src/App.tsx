import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import TopicPage from "./pages/TopicPage";
import GraphView from "./components/GraphView";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/page/:articleId" element={<TopicPage />} />
        <Route path="/graph" element={<GraphView />} />
        <Route path="/graph/:articleId" element={<GraphView />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
